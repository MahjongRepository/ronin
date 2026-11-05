from lobby.monitoring.gauges import MAX_BUCKETS
from lobby.monitoring.geometry import plot_buckets
from lobby.monitoring.page import ChartState, read_charts
from lobby.monitoring.ranges import MonitoringRange
from lobby.monitoring.reader import MetricsReader
from lobby.tests.conftest import create_metrics_db, insert_metric_rows

GIB = 2**30
NOW = 1_800_000_005


def _memory_rows(timestamps, *, used_gib):
    return [
        {"timestamp": timestamp, "boot": "b1", "used": used_gib * GIB, "available": GIB, "total": 8 * GIB}
        for timestamp in timestamps
    ]


async def _memory_used_chart(metrics_db, selected):
    charts = await read_charts(selected, metrics=MetricsReader(metrics_db), now=NOW)
    return next(chart for chart in charts if chart.name == "memory_used")


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
