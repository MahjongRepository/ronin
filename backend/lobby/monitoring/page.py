from __future__ import annotations

import functools
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from lobby.game_transition import fetch_game_server_status
from lobby.monitoring.gauges import GAUGES, bucket_window, read_gauge
from lobby.monitoring.reader import ReadFailure

if TYPE_CHECKING:
    import httpx

    from lobby.game_transition import GameServerStatus
    from lobby.monitoring.gauges import ChartGroup, ChartUnit, Gauge, GaugeRows
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
    A series' newest non-null sample in the chart's display unit, and how many seconds old it is.
    """

    value: float
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


def _empty_chart(gauge: Gauge, state: ChartState) -> Chart:
    return Chart(group=gauge.group, name=gauge.name, unit=gauge.unit, state=state, latest=None, buckets=())


def _gauge_chart(gauge: Gauge, rows: GaugeRows | ReadFailure, *, now: int) -> Chart:
    """
    Turn a gauge's rows into its chart, scaled to the display unit, with the state its own latest sample gives.
    """
    if isinstance(rows, ReadFailure):
        return _empty_chart(gauge, _FAILURE_STATES[rows])

    if rows.latest_value is None or rows.latest_at is None:
        return _empty_chart(gauge, ChartState.NEVER_COLLECTED)

    divisor = gauge.unit.divisor
    age_seconds = max(now - rows.latest_at, 0)
    return Chart(
        group=gauge.group,
        name=gauge.name,
        unit=gauge.unit,
        state=ChartState.STALE if age_seconds > STALE_AFTER_SECONDS else ChartState.CURRENT,
        latest=LatestReading(value=rows.latest_value / divisor, age_seconds=age_seconds),
        buckets=tuple(None if value is None else value / divisor for value in rows.buckets),
    )


async def read_charts(selected: MonitoringRange, *, metrics: MetricsReader, now: int) -> tuple[Chart, ...]:
    """
    Read every chart of the range ending at ``now`` (Unix seconds) from ``metrics.db``.
    """
    window = bucket_window(selected.duration, now=now)
    results = await metrics.run_each([functools.partial(read_gauge, gauge=gauge, window=window) for gauge in GAUGES])
    return tuple(_gauge_chart(gauge, rows, now=now) for gauge, rows in zip(GAUGES, results, strict=True))


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
