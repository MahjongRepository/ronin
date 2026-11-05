from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lobby.monitoring.page import Chart, MonitoringPage
    from lobby.monitoring.ranges import MonitoringRange

GAME_SERVER_UNAVAILABLE = "unavailable"


def _bucketed(chart: Chart) -> dict[str, object] | None:
    """
    Summarize a chart's buckets: how many there are, how many hold nothing, and the mean and maximum of the rest.
    """
    if not chart.buckets:
        return None

    values = [value for value in chart.buckets if value is not None]
    return {
        "buckets": len(chart.buckets),
        "empty_buckets": len(chart.buckets) - len(values),
        "mean": statistics.fmean(values) if values else None,
        "max": max(values, default=None),
    }


def _chart_report(chart: Chart) -> dict[str, object]:
    return {
        "name": chart.name,
        "unit": chart.unit.value,
        "state": chart.state.value,
        "latest": None
        if chart.latest is None
        else {"value": chart.latest.value, "age_seconds": chart.latest.age_seconds},
        "bucketed": _bucketed(chart),
        "retention_days": chart.retention_days,
    }


def monitoring_report(page: MonitoringPage, *, selected: MonitoringRange) -> dict[str, object]:
    """
    Turn the monitoring page's data into a JSON-ready document: the charts by group in the page's order, the games
    started in the range, the game server's live counts and the backup's age.

    A missing value, an empty bucket's value and an unknown age are None, never 0.
    """
    groups: dict[str, list[dict[str, object]]] = {}
    for chart in page.charts:
        groups.setdefault(chart.group.value, []).append(_chart_report(chart))

    return {
        "range": selected.value,
        "chart_groups": groups,
        "last_backup_age_seconds": page.last_backup_age_seconds,
        "games": page.games.model_dump(mode="json"),
        "live_status": GAME_SERVER_UNAVAILABLE
        if page.live_status is None
        else page.live_status.model_dump(mode="json"),
    }
