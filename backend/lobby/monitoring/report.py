from __future__ import annotations

import statistics
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from lobby.monitoring.geometry import PLOT_HEIGHT, PLOT_WIDTH, plot_buckets
from lobby.monitoring.ranges import MonitoringRange

if TYPE_CHECKING:
    from lobby.monitoring.page import Chart, MonitoringPage

GAME_SERVER_UNAVAILABLE = "unavailable"
_SECONDS_PER_DAY = 86400
_CLOCK_FORMAT = "%H:%M"
_DAY_FORMAT = "%m-%d"
_DAY_AND_CLOCK_FORMAT = "%m-%d %H:%M"
_DAY_ONLY_AFTER_DAYS = 3


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


def _plot(chart: Chart) -> dict[str, object] | None:
    plot = plot_buckets(chart.buckets)
    if plot is None:
        return None

    return {"lines": list(plot.lines), "axis_maximum": plot.axis_maximum}


def _time_axis(charted_from: int, charted_to: int) -> list[str]:
    """
    Label the charts' start, middle and end in UTC: clock times within a day, days with times up to
    ``_DAY_ONLY_AFTER_DAYS``, days alone beyond.
    """
    span = charted_to - charted_from
    if span <= _SECONDS_PER_DAY:
        time_format = _CLOCK_FORMAT
    elif span <= _DAY_ONLY_AFTER_DAYS * _SECONDS_PER_DAY:
        time_format = _DAY_AND_CLOCK_FORMAT
    else:
        time_format = _DAY_FORMAT

    return [
        datetime.fromtimestamp(timestamp, UTC).strftime(time_format)
        for timestamp in (charted_from, charted_from + span // 2, charted_to)
    ]


def _collected_since(page: MonitoringPage) -> str | None:
    """
    Label in UTC when the charts start, if that is the collector's oldest sample rather than the range's start.
    """
    if not page.starts_at_oldest_sample:
        return None

    return datetime.fromtimestamp(page.charted_from, UTC).strftime(_DAY_AND_CLOCK_FORMAT)


def _chart_report(chart: Chart, *, with_plot: bool) -> dict[str, object]:
    report: dict[str, object] = {
        "name": chart.name,
        "unit": chart.unit.value,
        "state": chart.state.value,
        "latest": None
        if chart.latest is None
        else {"value": chart.latest.value, "age_seconds": chart.latest.age_seconds},
        "bucketed": _bucketed(chart),
        "retention_days": chart.retention_days,
    }
    if with_plot:
        report["plot"] = _plot(chart)

    return report


def monitoring_report(page: MonitoringPage, *, selected: MonitoringRange, with_plots: bool) -> dict[str, object]:
    """
    Turn the monitoring page's data into a JSON-ready document: the charts by group in the page's order, the games
    started in the range, the game server's live counts and the backup's age, plus the range choices, the UTC time axis
    and the collection start when the charts begin there.

    ``with_plots`` adds what only the page draws: each chart's plot and the plot box.

    A missing value, an empty bucket's value and an unknown age are None, never 0.
    """
    groups: dict[str, list[dict[str, object]]] = {}
    for chart in page.charts:
        groups.setdefault(chart.group.value, []).append(_chart_report(chart, with_plot=with_plots))

    report: dict[str, object] = {
        "range": selected.value,
        "ranges": [choice.value for choice in MonitoringRange],
        "charted_from": page.charted_from,
        "charted_to": page.charted_to,
        "starts_at_oldest_sample": page.starts_at_oldest_sample,
        "collected_since": _collected_since(page),
        "time_axis": _time_axis(page.charted_from, page.charted_to),
        "chart_groups": groups,
        "last_backup_age_seconds": page.last_backup_age_seconds,
        "games": page.games.model_dump(mode="json"),
        "live_status": GAME_SERVER_UNAVAILABLE
        if page.live_status is None
        else page.live_status.model_dump(mode="json"),
    }
    if with_plots:
        report["plot_width"] = PLOT_WIDTH
        report["plot_height"] = PLOT_HEIGHT

    return report
