import logging
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest

from lobby.tests.conftest import create_metrics_db, insert_metric_rows
from lobby.tests.integration.conftest import grant_admin, register_with_csrf

GIB = 2**30
MIB = 2**20
CHART = re.compile(
    r'<figure class="monitoring-chart" data-chart="([\w.]+)" data-state="(\w+)">(.*?)</figure>', re.DOTALL
)


def _charts(page: str) -> dict[str, tuple[str, str]]:
    return {key: (state, body) for key, state, body in CHART.findall(page)}


def _chart_states(page: str) -> dict[str, str]:
    return {key: state for key, (state, _body) in _charts(page).items()}


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


class TestMonitoringPageCharts:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "opsuser")
        grant_admin(client, "opsuser")
        return client

    @pytest.fixture
    def metrics_db(self, client):
        return Path(client.app.state.settings.metrics_db_path)

    def test_monitoring_page__when_metrics_file_missing__should_show_every_chart_never_collected(self, client):
        response = client.get("/admin/monitoring")
        assert response.status_code == 200
        states = _chart_states(response.text)
        assert set(states.values()) == {"never_collected"}
        assert len(states) == 25
        assert {key.split(".")[0] for key in states} == {"host", "services", "game", "sockets", "traefik", "storage"}
        assert 'data-stat="last_backup">Unknown<' in response.text
        assert 'data-stat="started">0<' in response.text

    def test_monitoring_page__when_one_table_never_created__should_draw_the_rest_and_mark_its_charts_never_collected(
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

        response = client.get("/admin/monitoring?range=1h")
        assert response.status_code == 200
        charts = _charts(response.text)
        states = {key: state for key, (state, _body) in charts.items()}
        assert {key for key, state in states.items() if state == "current"} == {
            "host.memory_used",
            "host.disk_used",
            "storage.database",
        }
        assert {state for state in states.values() if state != "current"} == {"never_collected"}
        assert charts["host.memory_used"][1].count("<polyline") == 1
        assert "Latest 75%" in charts["host.memory_used"][1]
        assert "Latest 25%" in charts["host.disk_used"][1]
        assert "Latest 3 MiB" in charts["storage.database"][1]
        assert "Metrics collected since" in response.text
        assert 'data-stat="last_backup">Unknown<' in response.text

    def test_monitoring_page__when_metrics_file_is_not_a_database__should_show_charts_unavailable(
        self, client, metrics_db, caplog
    ):
        metrics_db.write_bytes(b"not a sqlite database at all" * 100)

        with caplog.at_level(logging.WARNING):
            response = client.get("/admin/monitoring")
        assert response.status_code == 200
        assert set(_chart_states(response.text).values()) == {"unavailable"}
        assert "metrics database read failed" in caplog.text
        assert 'data-stat="started">0<' in response.text

    def test_monitoring_page__when_one_service_stops_reporting__should_mark_only_its_chart_stale(
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

        response = client.get("/admin/monitoring?range=1h")
        assert response.status_code == 200
        charts = _charts(response.text)
        assert charts["services.lobby_memory"][0] == "current"
        assert charts["services.game_memory"][0] == "stale"
        assert charts["services.traefik_memory"][0] == "never_collected"
        assert "Stale" not in charts["services.lobby_memory"][1]
        assert "Stale: the last sample is 20m" in charts["services.game_memory"][1]
        assert charts["services.game_memory"][1].count("<polyline") == 1
        assert charts["services.lobby_cpu"][0] == "current"
        assert charts["services.game_cpu"][0] == "stale"
        assert "Latest 0.5, " in charts["services.lobby_cpu"][1]
        assert charts["services.lobby_cpu"][1].count("<polyline") == 1
        assert 'data-stat="last_backup">2h 0m ago<' in response.text
