from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from datetime import timedelta

MAX_BUCKETS = 300
SAMPLE_INTERVAL_SECONDS = 60
_BUCKET_EDGE_SECOND = 30


class ChartGroup(StrEnum):
    HOST = "host"
    SERVICES = "services"


class ChartUnit(StrEnum):
    """
    A chart's display unit; ``divisor`` turns a stored value into it.
    """

    PERCENT = "percent"
    GIB = "gib"
    MIB = "mib"

    @property
    def divisor(self) -> float:
        return _UNIT_DIVISORS[self]


_UNIT_DIVISORS = {ChartUnit.PERCENT: 1.0, ChartUnit.GIB: float(2**30), ChartUnit.MIB: float(2**20)}


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


def bucket_window(duration: timedelta, *, now: int) -> BucketWindow:
    """
    Split the ``duration`` up to ``now`` into at most ``MAX_BUCKETS`` buckets, the last one holding ``now``.
    """
    seconds = int(duration.total_seconds())
    width = SAMPLE_INTERVAL_SECONDS * math.ceil(seconds / (MAX_BUCKETS * SAMPLE_INTERVAL_SECONDS))
    end = now - (now - _BUCKET_EDGE_SECOND) % SAMPLE_INTERVAL_SECONDS + SAMPLE_INTERVAL_SECONDS
    count = math.ceil(seconds / width)
    return BucketWindow(start=end - count * width, width=width, count=count)


@dataclass(frozen=True)
class Gauge:
    """
    A chart of a sampled value: the stable ``group`` and ``name``, and the SQL that reads one series of it.

    ``value`` is a column expression of ``table`` and ``series`` the condition selecting the series' rows, with
    ``series_params`` bound to it; all three are constants of this module, never request input.
    """

    group: ChartGroup
    name: str
    unit: ChartUnit
    table: str
    value: str
    series: str = "1"
    series_params: tuple[str, ...] = ()


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
    Gauge(group=ChartGroup.HOST, name="memory_used", unit=ChartUnit.GIB, table="mem", value="used"),
    Gauge(group=ChartGroup.HOST, name="memory_available", unit=ChartUnit.GIB, table="mem", value="available"),
    Gauge(
        group=ChartGroup.HOST,
        name="disk_used",
        unit=ChartUnit.PERCENT,
        table="disk",
        value="100.0 * used / total",
        series="path = ?",
        series_params=("/",),
    ),
    _service_memory("traefik"),
    _service_memory("lobby"),
    _service_memory("game"),
)


@dataclass(frozen=True)
class GaugeRows:
    """
    A gauge series as read: each bucket's mean in stored units (None for a bucket without a sample), and the newest
    sample holding a value, at any time, with its Unix timestamp (None when the series has none).
    """

    buckets: tuple[float | None, ...]
    latest_value: float | None
    latest_at: int | None


def read_gauge(connection: sqlite3.Connection, *, gauge: Gauge, window: BucketWindow) -> GaugeRows:
    """
    Reduce the gauge's samples inside the window to one mean per bucket in SQL, and read its latest sample.
    """
    bucket_rows = connection.execute(
        f"SELECT (timestamp - ?) / ? AS bucket, avg(value) FROM ("  # noqa: S608 - module constants only
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
    return GaugeRows(
        buckets=tuple(means.get(index) for index in range(window.count)),
        latest_value=None if latest is None else latest[1],
        latest_at=None if latest is None else latest[0],
    )
