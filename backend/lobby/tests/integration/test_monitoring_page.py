import logging
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest

from tests.conftest import create_metrics_db, insert_metric_rows
from tests.integration.conftest import grant_admin, register_with_csrf

GIB = 2**30
MIB = 2**20
MONITORING_PATH = "/api/lobby/monitoring"


def _charts(report: dict) -> dict[str, dict]:
    return {f"{group}.{chart['name']}": chart for group, charts in report["chart_groups"].items() for chart in charts}


def _chart_states(report: dict) -> dict[str, str]:
    return {key: chart["state"] for key, chart in _charts(report).items()}


def _service_memory_rows(service: str, timestamps, *, used_mib: int):
    return [
        {
            "timestamp": timestamp,
            "boot": "b1",
            "path": f"/sys/fs/cgroup/ronin.slice/ronin-{service}.slice",
            "memory_current": used_mib * MIB,
            "memory_events_oom_kill": 0,
            "cpu_stat_usage_usec": timestamp * 500_000,
        }
        for timestamp in timestamps
    ]


class TestMonitoringDataCharts:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "opsuser")
        grant_admin(client, "opsuser")
        return client

    @pytest.fixture
    def metrics_db(self, client):
        return Path(client.app.state.settings.metrics_db_path)

    def test_monitoring_data__when_metrics_file_missing__should_report_every_chart_never_collected(self, client):
        response = client.get(MONITORING_PATH)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        report = response.json()
        states = _chart_states(report)
        assert set(states.values()) == {"never_collected"}
        assert len(states) == 25
        assert list(report["chart_groups"]) == ["host", "services", "game", "sockets", "traefik", "storage"]
        assert report["last_backup_age_seconds"] is None
        assert report["games"]["started"] == 0

    def test_monitoring_data__when_one_table_never_created__should_plot_the_rest_and_mark_its_charts_never_collected(
        self, client, metrics_db
    ):
        create_metrics_db(metrics_db)
        with closing(sqlite3.connect(metrics_db)) as conn, conn:
            conn.execute("DROP TABLE cgroup")
        now = int(time.time())
        insert_metric_rows(
            metrics_db,
            "mem",
            [
                {"timestamp": now - minutes * 60, "boot": "b1", "used": 3 * GIB, "available": GIB, "total": 4 * GIB}
                for minutes in range(10)
            ],
        )
        insert_metric_rows(
            metrics_db,
            "disk",
            [
                {
                    "timestamp": now,
                    "boot": "b1",
                    "device": "vda1",
                    "fstype": "ext4",
                    "label": "root",
                    "mode": "rw",
                    "path": "/",
                    "total": 80 * GIB,
                    "used": 20 * GIB,
                }
            ],
        )
        insert_metric_rows(
            metrics_db,
            "filestat",
            [
                {
                    "timestamp": now,
                    "boot": "b1",
                    "file": f"/opt/ronin/data/db/{name}",
                    "exists": 1,
                    "size_bytes": 3 * MIB,
                    "modification_time": now * 10**9,
                }
                for name in ("ronin.db", "ronin.db-wal")
            ],
        )

        response = client.get(MONITORING_PATH, params={"range": "1h"})
        assert response.status_code == 200
        report = response.json()
        charts = _charts(report)
        states = _chart_states(report)
        assert {key for key, state in states.items() if state == "current"} == {
            "host.memory_used",
            "host.disk_used",
            "storage.database",
        }
        assert {state for state in states.values() if state != "current"} == {"never_collected"}
        assert len(charts["host.memory_used"]["plot"]["lines"]) == 1
        assert charts["host.memory_used"]["plot"]["axis_maximum"] == 100
        assert charts["host.memory_used"]["latest"]["value"] == 75
        assert charts["host.disk_used"]["latest"]["value"] == 25
        assert charts["storage.database"]["latest"]["value"] == 3
        assert charts["services.lobby_memory"]["plot"] is None
        assert report["collected_since"] is not None
        assert report["last_backup_age_seconds"] is None

    def test_monitoring_data__when_metrics_file_is_not_a_database__should_report_charts_unavailable(
        self, client, metrics_db, caplog
    ):
        metrics_db.write_bytes(b"not a sqlite database at all" * 100)

        with caplog.at_level(logging.WARNING):
            response = client.get(MONITORING_PATH)
        assert response.status_code == 200
        assert set(_chart_states(response.json()).values()) == {"unavailable"}
        assert "metrics database read failed" in caplog.text
        assert response.json()["games"]["started"] == 0

    def test_monitoring_data__when_one_service_stops_reporting__should_mark_only_its_chart_stale(
        self, client, metrics_db
    ):
        create_metrics_db(metrics_db)
        now = int(time.time())
        insert_metric_rows(
            metrics_db, "cgroup", _service_memory_rows("lobby", range(now - 3600, now, 60), used_mib=120)
        )
        insert_metric_rows(
            metrics_db, "cgroup", _service_memory_rows("game", range(now - 3600, now - 1200 + 1, 60), used_mib=80)
        )
        insert_metric_rows(
            metrics_db,
            "filestat",
            [
                {
                    "timestamp": now - 60,
                    "boot": "b1",
                    "file": "/opt/ronin/data/metrics/last-backup",
                    "exists": 1,
                    "size_bytes": 0,
                    "modification_time": (now - 7200) * 10**9 + 123,
                }
            ],
        )

        response = client.get(MONITORING_PATH, params={"range": "1h"})
        assert response.status_code == 200
        report = response.json()
        charts = _charts(report)
        assert charts["services.lobby_memory"]["state"] == "current"
        assert charts["services.game_memory"]["state"] == "stale"
        assert charts["services.traefik_memory"]["state"] == "never_collected"
        assert charts["services.game_memory"]["latest"]["age_seconds"] // 60 == 20
        assert len(charts["services.game_memory"]["plot"]["lines"]) == 1
        assert charts["services.lobby_cpu"]["state"] == "current"
        assert charts["services.game_cpu"]["state"] == "stale"
        assert charts["services.lobby_cpu"]["latest"]["value"] == 0.5
        assert len(charts["services.lobby_cpu"]["plot"]["lines"]) == 1
        assert report["last_backup_age_seconds"] // 60 == 120


class TestMonitoringDataAccess:
    def test_monitoring_data__when_account_not_admin__should_answer_json_404(self, client):
        register_with_csrf(client, "playeruser")

        response = client.get(MONITORING_PATH)
        assert (response.status_code, response.json()) == (404, {"error": "not_found"})
        assert response.headers["cache-control"] == "no-store"
