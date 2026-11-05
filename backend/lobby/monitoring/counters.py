from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lobby.monitoring.gauges import SAMPLE_INTERVAL_SECONDS, BucketWindow, ChartGroup, ChartUnit, SeriesRows

if TYPE_CHECKING:
    import sqlite3

MAX_SAMPLE_SPACING_SECONDS = 90
_RESET_IDENTITIES = {"game_status": "boot || ' ' || started_at"}

TRAEFIK_RETENTION_DAYS = 30

_HOST_CPU_IDLE = "time_idle + time_iowait"
_HOST_CPU_BUSY = "time_user + time_nice + time_system + time_irq + time_softirq + time_steal"


@dataclass(frozen=True)
class Counter:
    """
    A chart of a raw counter read as a rate: the stable ``group`` and ``name``, and the SQL that reads it.

    ``value`` is the counter's column expression in ``table``, ``series`` the condition selecting its rows (with
    ``series_params`` bound to it) and ``series_key`` the expression telling apart the series of the table: every column
    ``series`` tests is part of it, so counters sharing a table and key are read in one pass. A bucket's value is the
    counter's delta over the delta of ``basis``, another counter of the same rows, or the plain delta when ``basis`` is
    None. A ``timestamp`` basis gives a rate per second, and the series' rates add up; for any other basis the deltas of
    every series are summed before dividing, so a mean (time per request) weighs each series by its count. All are
    constants of this module, never request input. A chart whose collector keeps ``retention_days`` of samples shows the
    older part of a longer range as never collected.
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
    retention_days: int | None = None


def _pressure(resource: str) -> Counter:
    return Counter(
        group=ChartGroup.HOST,
        name=f"pressure_{resource}",
        unit=ChartUnit.PERCENT,
        table="pressure",
        value="100.0 * total / 1e6",
        series_key="resource || ' ' || type",
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


def _game_status(group: ChartGroup, name: str, *, unit: ChartUnit, value: str, basis: str = "timestamp") -> Counter:
    return Counter(group=group, name=name, unit=unit, table="game_status", value=value, series_key="1", basis=basis)


def _game_per_minute(group: ChartGroup, column: str) -> Counter:
    return _game_status(group, column, unit=ChartUnit.PER_MINUTE, value=column)


_TRAEFIK_SERIES_KEY = "router || ' ' || code || ' ' || method || ' ' || protocol"
_PLAIN_HTTP_ROUTERS = "router NOT LIKE 'lobby-ws@%' AND router NOT LIKE 'game-ws@%'"
_GAME_SOCKET_ROUTER = "router LIKE 'game-ws@%'"
_TRAEFIK_COUNT = "traefik_router_request_duration_seconds_count"
_TRAEFIK_DURATION = "traefik_router_request_duration_seconds_sum"


def _traefik(name: str, *, unit: ChartUnit, value: str, series: str, basis: str = "timestamp") -> Counter:
    return Counter(
        group=ChartGroup.TRAEFIK,
        name=name,
        unit=unit,
        table="traefik",
        value=value,
        series_key=_TRAEFIK_SERIES_KEY,
        series=series,
        basis=basis,
        retention_days=TRAEFIK_RETENTION_DAYS,
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
    *(
        _game_per_minute(ChartGroup.GAME, column)
        for column in (
            "timeouts_turn",
            "timeouts_meld",
            "timeouts_round_advance",
            "ai_replacements",
            "reconnects",
            "takeovers",
            "resyncs",
        )
    ),
    _game_per_minute(ChartGroup.SOCKETS, "connections_accepted"),
    _game_status(ChartGroup.SOCKETS, "messages_in", unit=ChartUnit.PER_SECOND, value="messages_in"),
    _game_status(ChartGroup.SOCKETS, "messages_out", unit=ChartUnit.PER_SECOND, value="messages_out"),
    _game_status(ChartGroup.SOCKETS, "bytes_in", unit=ChartUnit.KIB_PER_SECOND, value="bytes_in"),
    _game_status(ChartGroup.SOCKETS, "bytes_out", unit=ChartUnit.KIB_PER_SECOND, value="bytes_out"),
    _game_status(
        ChartGroup.SOCKETS,
        "handling_time",
        unit=ChartUnit.MILLISECONDS,
        value="handling_seconds",
        basis="handled_messages",
    ),
    _game_per_minute(ChartGroup.SOCKETS, "malformed_messages"),
    _game_per_minute(ChartGroup.SOCKETS, "rate_limited_messages"),
    *(
        _game_per_minute(ChartGroup.SOCKETS, f"closes_{code}")
        for code in ("1000", "1008", "1011", "4001", "4002", "4004")
    ),
    _traefik(
        "response_time",
        unit=ChartUnit.MILLISECONDS,
        value=_TRAEFIK_DURATION,
        series=_PLAIN_HTTP_ROUTERS,
        basis=_TRAEFIK_COUNT,
    ),
    _traefik("requests", unit=ChartUnit.PER_MINUTE, value=_TRAEFIK_COUNT, series=_PLAIN_HTTP_ROUTERS),
    _traefik(
        "client_errors",
        unit=ChartUnit.PER_MINUTE,
        value=_TRAEFIK_COUNT,
        series=f"{_PLAIN_HTTP_ROUTERS} AND code LIKE '4%'",
    ),
    _traefik(
        "server_errors",
        unit=ChartUnit.PER_MINUTE,
        value=_TRAEFIK_COUNT,
        series=f"{_PLAIN_HTTP_ROUTERS} AND code LIKE '5%'",
    ),
    _traefik("game_sockets_closed", unit=ChartUnit.PER_MINUTE, value=_TRAEFIK_COUNT, series=_GAME_SOCKET_ROUTER),
    _traefik(
        "game_socket_lifetime",
        unit=ChartUnit.SECONDS,
        value=_TRAEFIK_DURATION,
        series=_GAME_SOCKET_ROUTER,
        basis=_TRAEFIK_COUNT,
    ),
)


def _counter_families(counters: tuple[Counter, ...]) -> tuple[tuple[Counter, ...], ...]:
    families: dict[tuple[str, str], list[Counter]] = {}
    for counter in counters:
        families.setdefault((counter.table, counter.series_key), []).append(counter)
    return tuple(tuple(family) for family in families.values())


COUNTER_FAMILIES = _counter_families(COUNTERS)


@dataclass(frozen=True)
class _FamilyColumns:
    """
    The distinct expressions of a family, each read and lagged once per sample however many counters share it.
    """

    values: tuple[str, ...]
    conditions: tuple[tuple[str, tuple[str, ...]], ...]

    @classmethod
    def of(cls, family: tuple[Counter, ...]) -> _FamilyColumns:
        values = dict.fromkeys(
            expression
            for counter in family
            for expression in (counter.value, counter.basis)
            if expression not in {None, "timestamp"}
        )
        conditions = dict.fromkeys((counter.series, counter.series_params) for counter in family)
        return cls(values=tuple(values), conditions=tuple(conditions))

    def value(self, expression: str) -> int:
        return self.values.index(expression)

    def condition(self, counter: Counter) -> int:
        return self.conditions.index((counter.series, counter.series_params))


def _counter_rate(counter: Counter, columns: _FamilyColumns) -> str:
    """
    Return the SQL of the counter's bucket value over the per-series bucket sums, None for a bucket holding an invalid
    interval of any of its series.
    """
    selected = f"FILTER (WHERE in_{columns.condition(counter)})"
    value = columns.value(counter.value)
    rising = [f"rising_{value}"]
    if counter.basis is None:
        rate = f"sum(delta_{value}) {selected}"
    elif counter.basis == "timestamp":
        rate = f"sum(CAST(delta_{value} AS REAL) / seconds) {selected}"
    else:
        basis = columns.value(counter.basis)
        rising.append(f"rising_{basis}")
        rate = f"CAST(sum(delta_{value}) {selected} AS REAL) / sum(delta_{basis}) {selected}"
    return f"CASE WHEN min(min(steady, {', '.join(rising)})) {selected} THEN {rate} END"


def _bucket_rates(
    connection: sqlite3.Connection, *, family: tuple[Counter, ...], window: BucketWindow
) -> list[dict[int, float | None]]:
    """
    Reduce the intervals ending inside the window to one rate per bucket that holds any, for each counter of a family
    (one table and series key) in one pass over its rows.

    Each sample is paired with its predecessor in the same series, the last one before the window included. A series'
    first sample ever has none and adds nothing, so a series first seen mid-range never empties a bucket, while a sample
    whose predecessor lies before the loaded rows ends a gap. An interval is invalid when the counter or its basis went
    down, the reset identity changed, or the samples are more than ``MAX_SAMPLE_SPACING_SECONDS`` apart; a bucket
    holding any invalid interval is None, so a reset or a short outage inside a long bucket still breaks the line.
    """
    table, series_key = family[0].table, family[0].series_key
    identity = _RESET_IDENTITIES.get(table, "boot")
    loaded_from = window.start - MAX_SAMPLE_SPACING_SECONDS
    columns = _FamilyColumns.of(family)
    values = list(enumerate(columns.values))
    conditions = [f"({condition}) AS in_{m}" for m, (condition, _params) in enumerate(columns.conditions)]
    sample_columns = ", ".join([*conditions, *(f"{expression} AS value_{j}" for j, expression in values)])
    lag_columns = ", ".join(f"lag(value_{j}) OVER previous AS previous_value_{j}" for j, _expression in values)
    bucket_columns = ", ".join(
        [
            *(f"in_{m}" for m in range(len(conditions))),
            *(
                f"sum(value_{j} - previous_value_{j}) AS delta_{j}, "
                f"min(coalesce(value_{j} >= previous_value_{j}, 0)) AS rising_{j}"
                for j, _expression in values
            ),
        ]
    )
    rate_columns = ", ".join(_counter_rate(counter, columns) for counter in family)
    rows = connection.execute(
        "WITH samples AS (SELECT * FROM ("  # noqa: S608 - module constants only
        f"SELECT timestamp, {series_key} AS series, {identity} AS identity, {sample_columns} FROM {table} "
        f"WHERE timestamp >= ? AND timestamp < ?) WHERE {' OR '.join(f'in_{m}' for m in range(len(conditions)))}"
        "), lagged AS ("
        "SELECT *, lag(timestamp) OVER previous AS previous_timestamp, "
        f"lag(identity) OVER previous AS previous_identity, {lag_columns} "
        "FROM samples WINDOW previous AS (PARTITION BY series ORDER BY timestamp)"
        "), series_buckets AS ("
        "SELECT (timestamp - ?) / ? AS bucket, sum(timestamp - previous_timestamp) AS seconds, "
        f"min(coalesce(timestamp - previous_timestamp <= {MAX_SAMPLE_SPACING_SECONDS} "
        f"AND identity = previous_identity, 0)) AS steady, {bucket_columns} "
        "FROM lagged WHERE timestamp >= ? AND (previous_timestamp IS NOT NULL OR EXISTS ("
        f"SELECT 1 FROM {table} WHERE timestamp < ? AND {series_key} = lagged.series)) GROUP BY bucket, series"
        f") SELECT bucket, {rate_columns} FROM series_buckets GROUP BY bucket",
        (
            *(param for _condition, params in columns.conditions for param in params),
            loaded_from,
            window.start + window.count * window.width,
            window.start,
            window.width,
            window.start,
            loaded_from,
        ),
    ).fetchall()
    return [{row[0]: row[i + 1] for row in rows} for i in range(len(family))]


def read_counter_family(
    connection: sqlite3.Connection, *, family: tuple[Counter, ...], window: BucketWindow
) -> list[SeriesRows]:
    """
    Reduce each counter of a family to one rate per bucket of the window in SQL, and read its newest sample.

    A counter's latest value is the rate of the intervals ending in the sample interval up to its newest sample, None
    when one of them is invalid.
    """
    rates = _bucket_rates(connection, family=family, window=window)
    return [
        _series_rows(connection, counter=counter, rates=counter_rates, window=window)
        for counter, counter_rates in zip(family, rates, strict=True)
    ]


def _series_rows(
    connection: sqlite3.Connection, *, counter: Counter, rates: dict[int, float | None], window: BucketWindow
) -> SeriesRows:
    latest = connection.execute(
        f"SELECT timestamp FROM {counter.table} "  # noqa: S608 - module constants only
        f"WHERE {counter.series} AND ({counter.value}) IS NOT NULL ORDER BY timestamp DESC LIMIT 1",
        counter.series_params,
    ).fetchone()
    if latest is None:
        return SeriesRows(buckets=(None,) * window.count, latest_value=None, latest_at=None)

    latest_at = latest[0]
    latest_window = BucketWindow(start=latest_at - SAMPLE_INTERVAL_SECONDS + 1, width=SAMPLE_INTERVAL_SECONDS, count=1)
    (latest_rates,) = _bucket_rates(connection, family=(counter,), window=latest_window)
    return SeriesRows(
        buckets=tuple(rates.get(index) for index in range(window.count)),
        latest_value=latest_rates.get(0),
        latest_at=latest_at,
    )
