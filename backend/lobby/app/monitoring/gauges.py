from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from datetime import timedelta

MAX_BUCKETS = 300
BACKUP_STAMP_NAME = "last-backup"
SAMPLE_INTERVAL_SECONDS = 60
_BUCKET_EDGE_SECOND = 30
SERVICES = ("traefik", "lobby", "game")


class ChartGroup(StrEnum):
    HOST = "host"
    SERVICES = "services"
    GAME = "game"
    SOCKETS = "sockets"
    TRAEFIK = "traefik"
    STORAGE = "storage"


class ChartUnit(StrEnum):
    """
    A chart's display unit; ``divisor`` turns a stored value into it.
    """

    PERCENT = "percent"
    MIB = "mib"
    CORES = "cores"
    COUNT = "count"
    PER_SECOND = "per_second"
    PER_MINUTE = "per_minute"
    MILLISECONDS = "milliseconds"

    @property
    def divisor(self) -> float:
        return _UNIT_DIVISORS[self]


_UNIT_DIVISORS = {
    ChartUnit.PERCENT: 1.0,
    ChartUnit.MIB: float(2**20),
    ChartUnit.CORES: 1.0,
    ChartUnit.COUNT: 1.0,
    ChartUnit.PER_SECOND: 1.0,
    ChartUnit.PER_MINUTE: 1 / 60,
    ChartUnit.MILLISECONDS: 1e-3,
}


@dataclass(frozen=True)
class BucketWindow:
    """
    A range split into ``count`` buckets of ``width`` seconds, the first starting at ``start`` (Unix seconds).

    The width is whole sample intervals and every edge falls half an interval away from the minute the collector samples
    on, so a sample a second or two late never leaves its bucket empty.
    """

    start: int
    width: int
    count: int


def bucket_window(duration: timedelta, *, now: int, collected_from: int | None) -> BucketWindow:
    """
    Split the ``duration`` up to ``now`` into at most ``MAX_BUCKETS`` buckets, the last one holding the sample of the
    latest whole minute at or before ``now``.

    A range reaching back past ``collected_from``, the collector's oldest sample, starts at it instead, so a history
    shorter than the range fills the chart rather than a sliver at its right edge.
    """
    end = now - now % SAMPLE_INTERVAL_SECONDS + _BUCKET_EDGE_SECOND
    seconds = int(duration.total_seconds())
    if collected_from is not None:
        seconds = max(min(seconds, end - collected_from), SAMPLE_INTERVAL_SECONDS)

    width = SAMPLE_INTERVAL_SECONDS * math.ceil(seconds / (MAX_BUCKETS * SAMPLE_INTERVAL_SECONDS))
    count = math.ceil(seconds / width)
    return BucketWindow(start=end - count * width, width=width, count=count)


def read_collected_from(connection: sqlite3.Connection) -> int | None:
    """
    Return the Unix timestamp of the collector's oldest host memory sample, sampled every run, or None before the first.
    """
    (oldest,) = connection.execute("SELECT min(timestamp) FROM mem").fetchone()
    return oldest


@dataclass(frozen=True)
class Gauge:
    """
    A chart of a sampled value: the stable ``group`` and ``name``, and the SQL that reads one series of it.

    ``value`` is a column expression of ``table`` and ``series`` the condition selecting the series' rows, with
    ``series_params`` bound to it; all three are constants of this module, never request input. A bucket takes the mean
    of its samples, or their maximum when ``bucket_peak`` is set, so one spike is never averaged away.
    """

    group: ChartGroup
    name: str
    unit: ChartUnit
    table: str
    value: str
    series: str = "1"
    series_params: tuple[str, ...] = ()
    bucket_peak: bool = False


def _service_memory(service: str) -> Gauge:
    return Gauge(
        group=ChartGroup.SERVICES,
        name=f"{service}_memory",
        unit=ChartUnit.MIB,
        table="cgroup",
        value="memory_current",
        series="path LIKE ?",
        series_params=(f"%/ronin-{service}.slice",),
    )


GAUGES = (
    Gauge(group=ChartGroup.HOST, name="memory_used", unit=ChartUnit.PERCENT, table="mem", value="100.0 * used / total"),
    Gauge(
        group=ChartGroup.HOST,
        name="disk_used",
        unit=ChartUnit.PERCENT,
        table="disk",
        value="100.0 * used / total",
        series="path = ?",
        series_params=("/",),
    ),
    *(_service_memory(service) for service in SERVICES),
    Gauge(group=ChartGroup.GAME, name="active_games", unit=ChartUnit.COUNT, table="game_status", value="active_games"),
    Gauge(
        group=ChartGroup.GAME,
        name="loop_lag_max",
        unit=ChartUnit.MILLISECONDS,
        table="game_status",
        value="loop_lag_max_ms / 1e3",
        bucket_peak=True,
    ),
    Gauge(group=ChartGroup.SOCKETS, name="open", unit=ChartUnit.COUNT, table="game_status", value="connections"),
    Gauge(
        group=ChartGroup.STORAGE,
        name="database",
        unit=ChartUnit.MIB,
        table="filestat",
        value="size_bytes",
        series=f"file NOT LIKE '%-wal' AND file NOT LIKE '%{BACKUP_STAMP_NAME}'",
    ),
    Gauge(group=ChartGroup.STORAGE, name="replays", unit=ChartUnit.MIB, table="filecount", value="size_bytes"),
)


@dataclass(frozen=True)
class SeriesRows:
    """
    A chart's series as read, in stored units: each bucket's value (None for a bucket with nothing to draw), and the
    latest value with the Unix timestamp of the newest sample holding one, at any time (None when the series has none).

    A gauge's latest value is that sample's; a counter's is the rate ending at it, None when that interval is invalid.
    """

    buckets: tuple[float | None, ...]
    latest_value: float | None
    latest_at: int | None


def read_gauge(connection: sqlite3.Connection, *, gauge: Gauge, window: BucketWindow) -> SeriesRows:
    """
    Reduce the gauge's samples inside the window to one mean (or peak) per bucket in SQL, and read its latest sample.
    """
    aggregate = "max" if gauge.bucket_peak else "avg"
    bucket_rows = connection.execute(
        f"SELECT (timestamp - ?) / ? AS bucket, {aggregate}(value) FROM ("  # noqa: S608 - module constants only
        f"SELECT timestamp, {gauge.value} AS value FROM {gauge.table} "
        f"WHERE timestamp >= ? AND timestamp < ? AND {gauge.series}"
        ") WHERE value IS NOT NULL GROUP BY bucket",
        (window.start, window.width, window.start, window.start + window.count * window.width, *gauge.series_params),
    ).fetchall()
    latest = connection.execute(
        f"SELECT timestamp, {gauge.value} FROM {gauge.table} "  # noqa: S608 - module constants only
        f"WHERE {gauge.series} AND ({gauge.value}) IS NOT NULL ORDER BY timestamp DESC LIMIT 1",
        gauge.series_params,
    ).fetchone()

    means = dict(bucket_rows)
    return SeriesRows(
        buckets=tuple(means.get(index) for index in range(window.count)),
        latest_value=None if latest is None else latest[1],
        latest_at=None if latest is None else latest[0],
    )
