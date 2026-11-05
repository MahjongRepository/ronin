import itertools

import pytest

from lobby.monitoring.gauges import MAX_BUCKETS
from lobby.monitoring.geometry import plot_buckets
from lobby.monitoring.page import ChartState, read_charts
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


async def _chart_named(metrics_db, selected, name):
    charts = await read_charts(selected, metrics=MetricsReader(metrics_db), now=NOW)
    return next(chart for chart in charts if chart.name == name)


async def _memory_used_chart(metrics_db, selected):
    return await _chart_named(metrics_db, selected, "memory_used")


async def test_read_charts__when_range_is_90_days_of_minute_samples__should_reduce_to_at_most_300_full_buckets(
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


async def test_read_charts__when_samples_stop_for_a_stretch__should_split_the_line_without_a_zero(tmp_path):
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


async def test_read_charts__when_counter_grows_steadily__should_give_its_rate_in_every_bucket(tmp_path):
    metrics_db = tmp_path / "metrics.db"
    create_metrics_db(metrics_db)
    start = NOW - 3600 - 120
    insert_metric_rows(
        metrics_db, "cgroup", _lobby_cpu_rows((t, 0.25 * (t - start), "b1") for t in range(start, NOW + 1, 60))
    )

    chart = await _chart_named(metrics_db, MonitoringRange.HOUR, "lobby_cpu")

    assert chart.state == ChartState.CURRENT
    assert len(chart.buckets) == 60
    assert chart.buckets == pytest.approx([0.25] * 60)
    assert chart.latest is not None
    assert chart.latest.value == pytest.approx(0.25)


@pytest.mark.parametrize("disruption", ["counter_decrease", "identity_change_with_higher_counter", "missing_sample"])
async def test_read_charts__when_counter_is_disrupted_inside_a_long_bucket__should_empty_only_that_bucket(
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


async def test_read_charts__when_intervals_differ_in_length__should_weight_each_bucket_by_duration(tmp_path):
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
