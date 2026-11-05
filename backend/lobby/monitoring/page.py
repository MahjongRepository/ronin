from __future__ import annotations

import functools
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from lobby.game_transition import fetch_game_server_status
from lobby.monitoring.counters import COUNTERS, read_counter
from lobby.monitoring.gauges import GAUGES, bucket_window, read_gauge
from lobby.monitoring.reader import ReadFailure

if TYPE_CHECKING:
    import httpx

    from lobby.game_transition import GameServerStatus
    from lobby.monitoring.counters import Counter
    from lobby.monitoring.gauges import ChartGroup, ChartUnit, Gauge, SeriesRows
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

    A never-collected or unavailable chart has no latest reading and no buckets.
    """

    group: ChartGroup
    name: str
    unit: ChartUnit
    state: ChartState
    latest: LatestReading | None
    buckets: tuple[float | None, ...]


@dataclass(frozen=True)
class MonitoringPage:
    """
    Everything the monitoring page shows for a range; ``live_status`` is None when the game server did not answer.
    """

    charts: tuple[Chart, ...]
    games: GamesSummary
    live_status: GameServerStatus | None


def _empty_chart(spec: Gauge | Counter, state: ChartState) -> Chart:
    return Chart(group=spec.group, name=spec.name, unit=spec.unit, state=state, latest=None, buckets=())


def _chart(spec: Gauge | Counter, rows: SeriesRows | ReadFailure, *, now: int) -> Chart:
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
    )


async def read_charts(selected: MonitoringRange, *, metrics: MetricsReader, now: int) -> tuple[Chart, ...]:
    """
    Read every chart of the range ending at ``now`` (Unix seconds) from ``metrics.db``.
    """
    window = bucket_window(selected.duration, now=now)
    results = await metrics.run_each(
        [
            *(functools.partial(read_gauge, gauge=gauge, window=window) for gauge in GAUGES),
            *(functools.partial(read_counter, counter=counter, window=window) for counter in COUNTERS),
        ]
    )
    specs = (*GAUGES, *COUNTERS)
    return tuple(_chart(spec, rows, now=now) for spec, rows in zip(specs, results, strict=True))


async def assemble_monitoring_page(
    selected: MonitoringRange,
    *,
    metrics: MetricsReader,
    game_repo: GameRepository,
    game_server: httpx.AsyncClient,
) -> MonitoringPage:
    """
    Gather the monitoring page for a range: the charts, the games started in it and the game server's live counts.
    """
    now = datetime.now(UTC)
    charts = await read_charts(selected, metrics=metrics, now=int(now.timestamp()))
    games = await game_repo.get_games_summary(since=now - selected.duration)
    live_status = await fetch_game_server_status(game_server=game_server)
    return MonitoringPage(charts=charts, games=games, live_status=live_status)
