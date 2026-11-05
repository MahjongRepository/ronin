from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lobby.monitoring.gauges import SAMPLE_INTERVAL_SECONDS, BucketWindow, ChartGroup, ChartUnit, SeriesRows

if TYPE_CHECKING:
    import sqlite3

MAX_SAMPLE_SPACING_SECONDS = 90
_RESET_IDENTITIES = {"game_status": "boot || ' ' || started_at"}

_HOST_CPU_IDLE = "time_idle + time_iowait"
_HOST_CPU_BUSY = "time_user + time_nice + time_system + time_irq + time_softirq + time_steal"


@dataclass(frozen=True)
class Counter:
    """
    A chart of a raw counter read as a rate: the stable ``group`` and ``name``, and the SQL that reads it.

    ``value`` is the counter's column expression in ``table``, ``series`` the condition selecting its rows (with
    ``series_params`` bound to it) and ``series_key`` the expression telling apart the selected series, whose rates are
    added up. A bucket's value is the counter's delta over the delta of ``basis``, another counter of the same rows
    (``timestamp`` gives a rate per second), or the plain delta when ``basis`` is None. All are constants of this
    module, never request input.
    """

    group: ChartGroup
    name: str
    unit: ChartUnit
    table: str
    value: str
    series_key: str
    series: str = "1"
    series_params: tuple[str, ...] = ()
    basis: str | None = "timestamp"


def _pressure(resource: str) -> Counter:
    return Counter(
        group=ChartGroup.HOST,
        name=f"pressure_{resource}",
        unit=ChartUnit.PERCENT,
        table="pressure",
        value="100.0 * total / 1e6",
        series_key="resource",
        series="resource = ? AND type = 'some'",
        series_params=(resource,),
    )


def _service_counter(service: str, *, name: str, unit: ChartUnit, value: str, basis: str | None) -> Counter:
    return Counter(
        group=ChartGroup.SERVICES,
        name=f"{service}_{name}",
        unit=unit,
        table="cgroup",
        value=value,
        series_key="path",
        series="path LIKE ?",
        series_params=(f"%/ronin-{service}.slice",),
        basis=basis,
    )


COUNTERS = (
    Counter(
        group=ChartGroup.HOST,
        name="cpu_busy",
        unit=ChartUnit.PERCENT,
        table="cpu",
        value=f"100.0 * ({_HOST_CPU_BUSY})",
        series_key="cpu",
        basis=f"{_HOST_CPU_BUSY} + {_HOST_CPU_IDLE}",
    ),
    Counter(
        group=ChartGroup.HOST,
        name="network_in",
        unit=ChartUnit.KIB_PER_SECOND,
        table="net",
        value="bytes_recv",
        series_key="interface",
    ),
    Counter(
        group=ChartGroup.HOST,
        name="network_out",
        unit=ChartUnit.KIB_PER_SECOND,
        table="net",
        value="bytes_sent",
        series_key="interface",
    ),
    _pressure("cpu"),
    _pressure("memory"),
    _pressure("io"),
    *(
        _service_counter(
            service, name="cpu", unit=ChartUnit.CORES, value="cpu_stat_usage_usec / 1e6", basis="timestamp"
        )
        for service in ("traefik", "lobby", "game")
    ),
    *(
        _service_counter(service, name="oom_kills", unit=ChartUnit.COUNT, value="memory_events_oom_kill", basis=None)
        for service in ("traefik", "lobby", "game")
    ),
)


def _bucket_rates(connection: sqlite3.Connection, *, counter: Counter, window: BucketWindow) -> dict[int, float | None]:
    """
    Reduce the counter's intervals ending inside the window to one rate per bucket that holds any.

    Each sample is paired with its predecessor in the same series, the last one before the window included. An interval
    is invalid when the counter or its basis went down, the reset identity changed, or the samples are more than
    ``MAX_SAMPLE_SPACING_SECONDS`` apart; a bucket holding any invalid interval is None, so a reset or a short outage
    inside a long bucket still breaks the line.
    """
    identity = _RESET_IDENTITIES.get(counter.table, "boot")
    basis = counter.basis or "0"
    rate = "sum(delta)" if counter.basis is None else "CAST(sum(delta) AS REAL) / sum(basis_delta)"
    end = window.start + window.count * window.width
    rows = connection.execute(
        "WITH samples AS ("  # noqa: S608 - module constants only
        f"SELECT timestamp, {counter.series_key} AS series, {identity} AS identity, "
        f"{counter.value} AS value, {basis} AS basis FROM {counter.table} "
        f"WHERE timestamp >= ? AND timestamp < ? AND {counter.series}"
        "), intervals AS ("
        "SELECT timestamp, series, value - lag(value) OVER previous AS delta, "
        "basis - lag(basis) OVER previous AS basis_delta, "
        "coalesce(timestamp - lag(timestamp) OVER previous <= ? AND identity = lag(identity) OVER previous "
        "AND value >= lag(value) OVER previous AND basis >= lag(basis) OVER previous, 0) AS valid "
        "FROM samples WINDOW previous AS (PARTITION BY series ORDER BY timestamp)"
        "), series_buckets AS ("
        f"SELECT (timestamp - ?) / ? AS bucket, min(valid) AS valid, {rate} AS rate "
        "FROM intervals WHERE timestamp >= ? GROUP BY bucket, series"
        ") SELECT bucket, CASE WHEN min(valid) THEN sum(rate) END FROM series_buckets GROUP BY bucket",
        (
            window.start - MAX_SAMPLE_SPACING_SECONDS,
            end,
            *counter.series_params,
            MAX_SAMPLE_SPACING_SECONDS,
            window.start,
            window.width,
            window.start,
        ),
    ).fetchall()
    return dict(rows)


def read_counter(connection: sqlite3.Connection, *, counter: Counter, window: BucketWindow) -> SeriesRows:
    """
    Reduce the counter to one rate per bucket of the window in SQL, and read its newest sample.

    The latest value is the rate of the intervals ending in the sample interval up to that sample, None when one of them
    is invalid.
    """
    latest = connection.execute(
        f"SELECT timestamp FROM {counter.table} "  # noqa: S608 - module constants only
        f"WHERE {counter.series} AND ({counter.value}) IS NOT NULL ORDER BY timestamp DESC LIMIT 1",
        counter.series_params,
    ).fetchone()
    if latest is None:
        return SeriesRows(buckets=(None,) * window.count, latest_value=None, latest_at=None)

    rates = _bucket_rates(connection, counter=counter, window=window)
    latest_at = latest[0]
    latest_window = BucketWindow(start=latest_at - SAMPLE_INTERVAL_SECONDS + 1, width=SAMPLE_INTERVAL_SECONDS, count=1)
    return SeriesRows(
        buckets=tuple(rates.get(index) for index in range(window.count)),
        latest_value=_bucket_rates(connection, counter=counter, window=latest_window).get(0),
        latest_at=latest_at,
    )
