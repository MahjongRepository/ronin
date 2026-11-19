import json

import pytest

from lobby.monitoring.page import MonitoringPage, read_metrics
from lobby.monitoring.ranges import MonitoringRange
from lobby.monitoring.reader import MetricsReader
from lobby.monitoring.report import monitoring_report
from lobby.tests.conftest import create_metrics_db, insert_metric_rows
from shared.dal.models import GamesSummary

GIB = 2**30
NOW = 1_800_000_005


async def test_monitoring_report__when_one_table_has_a_gap__should_report_values_gap_and_never_collected_as_null(
    tmp_path,
):
    metrics_db = tmp_path / "metrics.db"
    create_metrics_db(metrics_db)
    hour = int(MonitoringRange.HOUR.duration.total_seconds())
    insert_metric_rows(
        metrics_db,
        "mem",
        [
            {
                "timestamp": timestamp,
                "boot": "b1",
                "used": (2 if timestamp < NOW - 1800 else 4) * GIB,
                "available": GIB,
                "total": 8 * GIB,
            }
            for timestamp in range(NOW - hour, NOW + 1, 60)
            if not NOW - 1800 <= timestamp < NOW - 1200
        ],
    )
    readings = await read_metrics(MonitoringRange.HOUR, metrics=MetricsReader(metrics_db), now=NOW)
    page = MonitoringPage(
        charts=readings.charts,
        charted_from=readings.charted_from,
        charted_to=readings.charted_to,
        starts_at_oldest_sample=readings.starts_at_oldest_sample,
        games=GamesSummary.from_timings([]),
        live_status=None,
        last_backup_age_seconds=readings.last_backup_age_seconds,
    )

    report = json.loads(json.dumps(monitoring_report(page, selected=MonitoringRange.HOUR, with_plots=True)))
    report_without_plots = json.loads(
        json.dumps(monitoring_report(page, selected=MonitoringRange.HOUR, with_plots=False))
    )

    memory_used = next(chart for chart in report["chart_groups"]["host"] if chart["name"] == "memory_used")
    assert memory_used["state"] == "current"
    assert memory_used["latest"] == {"value": 50.0, "age_seconds": 0}
    assert memory_used["bucketed"] == {
        "buckets": 60,
        "empty_buckets": 10,
        "mean": pytest.approx((29 * 25 + 21 * 50) / 50),
        "max": 50.0,
    }
    assert [line.split()[0] for line in memory_used["plot"]["lines"]] == ["2.50,50.00", "197.50,3.00"]
    assert memory_used["plot"]["axis_maximum"] == 50
    assert report["starts_at_oldest_sample"] is False
    assert report["collected_since"] is None
    assert report["time_axis"] == ["07:00", "07:30", "08:00"]
    assert {chart["state"] for chart in report["chart_groups"]["storage"]} == {"never_collected"}
    assert {(chart["latest"], chart["bucketed"], chart["plot"]) for chart in report["chart_groups"]["storage"]} == {
        (None, None, None)
    }
    assert report["last_backup_age_seconds"] is None
    assert report["live_status"] == "unavailable"
    assert (report["plot_width"], report["plot_height"]) == (300, 100)
    assert report_without_plots.keys() == report.keys() - {"plot_width", "plot_height"}
    assert [list(chart) for chart in report_without_plots["chart_groups"]["host"]] == [
        [key for key in chart if key != "plot"] for chart in report["chart_groups"]["host"]
    ]
