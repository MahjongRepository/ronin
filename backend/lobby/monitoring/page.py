from __future__ import annotations

import functools
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from lobby.game_transition import fetch_game_server_status
from lobby.monitoring.backup import read_backup_stamp
from lobby.monitoring.counters import COUNTER_FAMILIES, Counter, read_counter_family
from lobby.monitoring.gauges import GAUGES, ChartGroup, bucket_window, read_gauge
from lobby.monitoring.reader import ReadFailure

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable
    from datetime import timedelta

    import httpx

    from lobby.game_transition import GameServerStatus
    from lobby.monitoring.gauges import BucketWindow, ChartUnit, Gauge, SeriesRows
    from lobby.monitoring.ranges import MonitoringRange
    from lobby.monitoring.reader import MetricsReader
    from shared.dal.game_repository import GameRepository
    from shared.dal.models import GamesSummary

STALE_AFTER_SECONDS = 180


class ChartState(StrEnum):
    """
    How current a chart is, judged from its own series: a fresh row of another series never makes it current.
    """

    CURRENT = "current"
    STALE = "stale"
    NEVER_COLLECTED = "never_collected"
    UNAVAILABLE = "unavailable"


_FAILURE_STATES = {
    ReadFailure.NEVER_COLLECTED: ChartState.NEVER_COLLECTED,
    ReadFailure.UNAVAILABLE: ChartState.UNAVAILABLE,
}


@dataclass(frozen=True)
class LatestReading:
    """
    A series' latest value in the chart's display unit, and how many seconds old its newest sample is.

    ``value`` is None when that sample gives no valid reading, as a counter's first sample after a reset.
    """

    value: float | None
    age_seconds: int


@dataclass(frozen=True)
class Chart:
    """
    One chart's data in its display unit: each bucket's value, None for a bucket with nothing to draw.

    A never-collected or unavailable chart has no latest reading and no buckets. ``retention_days`` is how long the
    collector keeps the chart's samples when the range reaches further back, so its older part was never collected; None
    otherwise.
    """

    group: ChartGroup
    name: str
    unit: ChartUnit
    state: ChartState
    latest: LatestReading | None
    buckets: tuple[float | None, ...]
    retention_days: int | None = None


@dataclass(frozen=True)
class MonitoringPage:
    """
    Everything the monitoring page shows for a range; ``live_status`` is None when the game server did not answer, and
    ``last_backup_age_seconds`` when the backup's age is unknown.
    """

    charts: tuple[Chart, ...]
    games: GamesSummary
    live_status: GameServerStatus | None
    last_backup_age_seconds: int | None


def _empty_chart(spec: Gauge | Counter, state: ChartState) -> Chart:
    return Chart(group=spec.group, name=spec.name, unit=spec.unit, state=state, latest=None, buckets=())


def _retention_days(spec: Gauge | Counter, duration: timedelta) -> int | None:
    if not isinstance(spec, Counter) or spec.retention_days is None:
        return None

    return spec.retention_days if duration.days > spec.retention_days else None


def _chart(spec: Gauge | Counter, rows: SeriesRows | ReadFailure, *, now: int, duration: timedelta) -> Chart:
    """
    Turn a series' rows into its chart, scaled to the display unit, with the state its own newest sample gives.
    """
    if isinstance(rows, ReadFailure):
        return _empty_chart(spec, _FAILURE_STATES[rows])

    if rows.latest_at is None:
        return _empty_chart(spec, ChartState.NEVER_COLLECTED)

    divisor = spec.unit.divisor
    age_seconds = max(now - rows.latest_at, 0)
    return Chart(
        group=spec.group,
        name=spec.name,
        unit=spec.unit,
        state=ChartState.STALE if age_seconds > STALE_AFTER_SECONDS else ChartState.CURRENT,
        latest=LatestReading(
            value=None if rows.latest_value is None else rows.latest_value / divisor, age_seconds=age_seconds
        ),
        buckets=tuple(None if value is None else value / divisor for value in rows.buckets),
        retention_days=_retention_days(spec, duration),
    )


@dataclass(frozen=True)
class MetricsReadings:
    """
    What ``metrics.db`` gives the page: every chart in the display order, and how many seconds ago the last backup
    finished by its stamp's modification time (None when unknown).
    """

    charts: tuple[Chart, ...]
    last_backup_age_seconds: int | None


def _read_gauge_family(connection: sqlite3.Connection, *, gauge: Gauge, window: BucketWindow) -> list[SeriesRows]:
    return [read_gauge(connection, gauge=gauge, window=window)]


async def read_metrics(selected: MonitoringRange, *, metrics: MetricsReader, now: int) -> MetricsReadings:
    """
    Read every chart of the range ending at ``now`` (Unix seconds) and the backup stamp from ``metrics.db``.
    """
    window = bucket_window(selected.duration, now=now)
    families: list[tuple[Gauge | Counter, ...]] = [*((gauge,) for gauge in GAUGES), *COUNTER_FAMILIES]
    queries: list[Callable[[sqlite3.Connection], list[SeriesRows] | int | None]] = [
        *(functools.partial(_read_gauge_family, gauge=gauge, window=window) for gauge in GAUGES),
        *(functools.partial(read_counter_family, family=family, window=window) for family in COUNTER_FAMILIES),
        read_backup_stamp,
    ]
    *family_results, stamped_at = await metrics.run_each(queries)

    charts: list[Chart] = []
    for family, result in zip(families, family_results, strict=True):
        family_rows = [result] * len(family) if isinstance(result, ReadFailure) else cast("list[SeriesRows]", result)
        charts.extend(
            _chart(spec, rows, now=now, duration=selected.duration)
            for spec, rows in zip(family, family_rows, strict=True)
        )
    group_order = list(ChartGroup)
    return MetricsReadings(
        charts=tuple(sorted(charts, key=lambda chart: group_order.index(chart.group))),
        last_backup_age_seconds=max(now - stamped_at, 0) if isinstance(stamped_at, int) else None,
    )


async def assemble_monitoring_page(
    selected: MonitoringRange,
    *,
    metrics: MetricsReader,
    game_repo: GameRepository,
    game_server: httpx.AsyncClient,
) -> MonitoringPage:
    """
    Gather the monitoring page for a range: the charts, the backup's age, the games started in it and the game server's
    live counts.
    """
    now = datetime.now(UTC)
    readings = await read_metrics(selected, metrics=metrics, now=int(now.timestamp()))
    games = await game_repo.get_games_summary(since=now - selected.duration)
    live_status = await fetch_game_server_status(game_server=game_server)
    return MonitoringPage(
        charts=readings.charts,
        games=games,
        live_status=live_status,
        last_backup_age_seconds=readings.last_backup_age_seconds,
    )
