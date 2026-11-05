import itertools

import pytest

from lobby.monitoring.gauges import MAX_BUCKETS
from lobby.monitoring.geometry import plot_buckets
from lobby.monitoring.page import ChartState, read_metrics
from lobby.monitoring.ranges import MonitoringRange
from lobby.monitoring.reader import MetricsReader
from lobby.tests.conftest import create_metrics_db, insert_metric_rows

GIB = 2**30
NOW = 1_800_000_005
LOBBY_SLICE = "/sys/fs/cgroup/ronin.slice/ronin-lobby.slice"


def _memory_rows(timestamps, *, used_gib):
    return [
        {"timestamp": timestamp, "boot": "b1", "used": used_gib * GIB, "available": GIB, "total": 8 * GIB}
        for timestamp in timestamps
    ]


def _lobby_cpu_rows(samples):
    return [
        {
            "timestamp": timestamp,
            "boot": boot,
            "path": LOBBY_SLICE,
            "memory_current": GIB,
            "memory_events_oom_kill": 0,
            "cpu_stat_usage_usec": round(cpu_seconds * 1_000_000),
        }
        for timestamp, cpu_seconds, boot in samples
    ]


def _host_cpu_rows(timestamps):
    return [
        {
            "timestamp": timestamp,
            "boot": "b1",
            "cpu": "cpu-total",
            "time_user": 30.0 * minute,
            "time_nice": 0.0,
            "time_system": 15.0 * minute,
            "time_irq": 3.0 * minute,
            "time_softirq": 2.0 * minute,
            "time_steal": 0.0,
            "time_idle": 40.0 * minute,
            "time_iowait": 10.0 * minute,
            "time_guest": 50.0 * minute,
            "time_guest_nice": 0.0,
        }
        for minute, timestamp in enumerate(timestamps)
    ]


def _traefik_rows(router, code, timestamps, *, requests_per_sample, seconds_per_request):
    protocol = "websocket" if code == "0" else "http"
    return [
        {
            "timestamp": timestamp,
            "boot": "b1",
            "router": router,
            "code": code,
            "method": "GET",
            "protocol": protocol,
            "traefik_router_request_duration_seconds_count": requests_per_sample * sample,
            "traefik_router_request_duration_seconds_sum": requests_per_sample * sample * seconds_per_request,
        }
        for sample, timestamp in enumerate(timestamps, start=1)
    ]


async def _charts_named(metrics_db, selected, *names):
    charts = {
        chart.name: chart for chart in (await read_metrics(selected, metrics=MetricsReader(metrics_db), now=NOW)).charts
    }
    return [charts[name] for name in names]


async def _chart_named(metrics_db, selected, name):
    (chart,) = await _charts_named(metrics_db, selected, name)
    return chart


async def _memory_used_chart(metrics_db, selected):
    return await _chart_named(metrics_db, selected, "memory_used")


async def test_read_metrics__when_range_is_90_days_of_minute_samples__should_reduce_to_at_most_300_full_buckets(
    tmp_path,
):
    metrics_db = tmp_path / "metrics.db"
    create_metrics_db(metrics_db)
    ninety_days = int(MonitoringRange.QUARTER.duration.total_seconds())
    insert_metric_rows(metrics_db, "mem", _memory_rows(range(NOW - ninety_days, NOW + 1, 60), used_gib=2))

    chart = await _memory_used_chart(metrics_db, MonitoringRange.QUARTER)

    assert chart.state == ChartState.CURRENT
    assert len(chart.buckets) <= MAX_BUCKETS
    assert set(chart.buckets) == {2.0}


async def test_read_metrics__when_samples_stop_for_a_stretch__should_split_the_line_without_a_zero(tmp_path):
    metrics_db = tmp_path / "metrics.db"
    create_metrics_db(metrics_db)
    hour = int(MonitoringRange.HOUR.duration.total_seconds())
    sampled = [timestamp for timestamp in range(NOW - hour, NOW + 1, 60) if not NOW - 1800 <= timestamp < NOW - 1200]
    insert_metric_rows(metrics_db, "mem", _memory_rows(sampled, used_gib=4))

    chart = await _memory_used_chart(metrics_db, MonitoringRange.HOUR)
    plot = plot_buckets(chart.buckets)

    assert plot is not None
    assert len(plot.lines) == 2
    assert plot.axis_maximum == 5.0
    assert {point.split(",")[1] for line in plot.lines for point in line.split()} == {"20.00"}


async def test_read_metrics__when_counter_grows_steadily__should_give_its_rate_in_every_bucket(tmp_path):
    metrics_db = tmp_path / "metrics.db"
    create_metrics_db(metrics_db)
    start = NOW - 3600 - 120
    insert_metric_rows(
        metrics_db, "cgroup", _lobby_cpu_rows((t, 0.25 * (t - start), "b1") for t in range(start, NOW + 1, 60))
    )
    insert_metric_rows(metrics_db, "cpu", _host_cpu_rows(range(start, NOW + 1, 60)))

    chart, host_cpu = await _charts_named(metrics_db, MonitoringRange.HOUR, "lobby_cpu", "cpu_busy")

    assert chart.state == ChartState.CURRENT
    assert len(chart.buckets) == 60
    assert chart.buckets == pytest.approx([0.25] * 60)
    assert chart.latest is not None
    assert chart.latest.value == pytest.approx(0.25)
    assert host_cpu.buckets == pytest.approx([50.0] * 60)


@pytest.mark.parametrize("disruption", ["counter_decrease", "identity_change_with_higher_counter", "missing_sample"])
async def test_read_metrics__when_counter_is_disrupted_inside_a_long_bucket__should_empty_only_that_bucket(
    tmp_path, disruption
):
    metrics_db = tmp_path / "metrics.db"
    create_metrics_db(metrics_db)
    start = NOW - 86400 - 120
    disrupted_at = NOW - 3 * 3600 - 120
    samples = []
    for timestamp in range(start, NOW + 1, 60):
        if disruption == "missing_sample" and timestamp == disrupted_at:
            continue

        after = timestamp >= disrupted_at
        cpu_seconds = 0.25 * (timestamp - (disrupted_at if after and disruption == "counter_decrease" else start))
        boot = "b2" if after and disruption == "identity_change_with_higher_counter" else "b1"
        samples.append((timestamp, cpu_seconds, boot))
    insert_metric_rows(metrics_db, "cgroup", _lobby_cpu_rows(samples))

    chart = await _chart_named(metrics_db, MonitoringRange.DAY, "lobby_cpu")
    plot = plot_buckets(chart.buckets)

    assert chart.buckets.count(None) == 1
    assert [value for value in chart.buckets if value is not None] == pytest.approx([0.25] * (len(chart.buckets) - 1))
    assert plot is not None
    assert len(plot.lines) == 2


async def test_read_metrics__when_intervals_differ_in_length__should_weight_each_bucket_by_duration(tmp_path):
    metrics_db = tmp_path / "metrics.db"
    create_metrics_db(metrics_db)
    samples, timestamp, cpu_seconds = [], NOW - 8 * 86400, 0.0
    for seconds, cores in itertools.cycle([(40, 1.0), (80, 4.0)]):
        if timestamp > NOW:
            break

        samples.append((timestamp, cpu_seconds, "b1"))
        timestamp, cpu_seconds = timestamp + seconds, cpu_seconds + seconds * cores
    insert_metric_rows(metrics_db, "cgroup", _lobby_cpu_rows(samples))

    chart = await _chart_named(metrics_db, MonitoringRange.WEEK, "lobby_cpu")

    assert chart.buckets[:-1] == pytest.approx([3.0] * (len(chart.buckets) - 1))


async def test_read_metrics__when_traefik_series_differ__should_weigh_http_routers_by_count_and_skip_new_series(
    tmp_path,
):
    metrics_db = tmp_path / "metrics.db"
    create_metrics_db(metrics_db)
    hour = int(MonitoringRange.HOUR.duration.total_seconds())
    timestamps = range(NOW - hour - 120, NOW + 1, 60)
    window_start = NOW - NOW % 60 + 30 - hour
    cut_off_before_window_start = [t for t in timestamps if not window_start - 120 <= t < window_start]
    for rows in (
        _traefik_rows("lobby@file", "200", timestamps, requests_per_sample=6, seconds_per_request=0.01),
        _traefik_rows(
            "replay-api@file", "404", cut_off_before_window_start, requests_per_sample=2, seconds_per_request=0.1
        ),
        _traefik_rows(
            "lobby@file",
            "502",
            [t for t in timestamps if t >= NOW - 1800],
            requests_per_sample=1,
            seconds_per_request=0.0325,
        ),
        _traefik_rows("game-ws@file", "0", timestamps, requests_per_sample=1, seconds_per_request=600.0),
        _traefik_rows("lobby-ws@file", "0", timestamps, requests_per_sample=1, seconds_per_request=300.0),
    ):
        insert_metric_rows(metrics_db, "traefik", rows)

    response_time, server_errors, socket_lifetime = await _charts_named(
        metrics_db, MonitoringRange.HOUR, "response_time", "server_errors", "game_socket_lifetime"
    )

    assert response_time.buckets[0] is None
    assert response_time.buckets[1:] == pytest.approx([32.5] * (len(response_time.buckets) - 1))
    assert server_errors.latest is not None
    assert server_errors.latest.value == pytest.approx(1.0)
    assert socket_lifetime.buckets == pytest.approx([600.0] * len(socket_lifetime.buckets))


async def test_read_metrics__when_loop_lag_spikes_once_in_a_long_bucket__should_keep_the_spike(tmp_path):
    metrics_db = tmp_path / "metrics.db"
    create_metrics_db(metrics_db)
    spike_at = NOW - 3 * 3600
    insert_metric_rows(
        metrics_db,
        "game_status",
        [
            {"timestamp": timestamp, "boot": "b1", "loop_lag_max_ms": 900.0 if timestamp == spike_at else 5.0}
            for timestamp in range(NOW - 86400, NOW + 1, 60)
        ],
    )

    chart = await _chart_named(metrics_db, MonitoringRange.DAY, "loop_lag_max")

    assert max(chart.buckets) == pytest.approx(900.0)
    assert sorted(set(chart.buckets)) == pytest.approx([5.0, 900.0])
