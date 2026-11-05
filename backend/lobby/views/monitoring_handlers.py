from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from lobby.monitoring.gauges import ChartGroup
from lobby.monitoring.geometry import PLOT_HEIGHT, PLOT_WIDTH, plot_buckets
from lobby.monitoring.page import assemble_monitoring_page
from lobby.monitoring.ranges import DEFAULT_MONITORING_RANGE, MonitoringRange
from lobby.monitoring.reader import MetricsReader
from lobby.views.assets import render_page, translate_for_request
from lobby.views.history_handlers import format_duration_seconds

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.monitoring.geometry import ChartPlot
    from lobby.monitoring.page import Chart, ChartState, LatestReading
    from lobby.views.history_handlers import Translate
    from shared.dal.models import GamesSummary


@dataclass(frozen=True)
class _RangeChoice:
    url: str
    label: str
    is_current: bool


@dataclass(frozen=True)
class _CompletedDurations:
    mean: str
    median: str
    p90: str


@dataclass(frozen=True)
class _ChartView:
    key: str
    label_key: str
    unit_key: str
    state: ChartState
    latest: LatestReading | None
    age: str | None
    plot: ChartPlot | None
    retention_days: int | None


@dataclass(frozen=True)
class _ChartGroupView:
    label_key: str
    charts: tuple[_ChartView, ...]
    shows_last_backup: bool


def _selected_range(request: Request) -> MonitoringRange:
    """
    Return the page's range from ``?range=``, the default for a missing or unknown one.
    """
    try:
        return MonitoringRange(request.query_params.get("range", DEFAULT_MONITORING_RANGE))
    except ValueError:
        return DEFAULT_MONITORING_RANGE


def _range_choices(selected: MonitoringRange, *, translate: Translate) -> list[_RangeChoice]:
    return [
        _RangeChoice(url=f"?range={choice}", label=translate(choice.label_key), is_current=choice == selected)
        for choice in MonitoringRange
    ]


def _completed_durations(summary: GamesSummary, *, translate: Translate) -> _CompletedDurations | None:
    """
    Format the completed games' mean, median and p90 durations, or None when the range holds no completed game.
    """
    durations = summary.completed_durations
    if durations is None:
        return None

    return _CompletedDurations(
        mean=format_duration_seconds(durations.mean_seconds, translate=translate),
        median=format_duration_seconds(durations.median_seconds, translate=translate),
        p90=format_duration_seconds(durations.p90_seconds, translate=translate),
    )


def _chart_view(chart: Chart, *, translate: Translate) -> _ChartView:
    return _ChartView(
        key=f"{chart.group}.{chart.name}",
        label_key=f"monitoring.series.{chart.group}.{chart.name}",
        unit_key=f"monitoring.unit.{chart.unit}",
        state=chart.state,
        latest=chart.latest,
        age=None if chart.latest is None else format_duration_seconds(chart.latest.age_seconds, translate=translate),
        plot=plot_buckets(chart.buckets),
        retention_days=chart.retention_days,
    )


def _chart_groups(charts: tuple[Chart, ...], *, translate: Translate) -> list[_ChartGroupView]:
    """
    Group the charts for display, groups and charts in the order the page data lists them; the storage group also shows
    the last backup's age.
    """
    grouped: dict[ChartGroup, list[_ChartView]] = {}
    for chart in charts:
        grouped.setdefault(chart.group, []).append(_chart_view(chart, translate=translate))

    return [
        _ChartGroupView(
            label_key=f"monitoring.group.{group}", charts=tuple(views), shows_last_backup=group == ChartGroup.STORAGE
        )
        for group, views in grouped.items()
    ]


async def monitoring_page(request: Request) -> Response:
    """
    GET /admin/monitoring - render the monitoring page for ``?range=``: live and started games, and the charts.
    """
    translate = functools.partial(translate_for_request, request)
    selected = _selected_range(request)
    page = await assemble_monitoring_page(
        selected,
        metrics=MetricsReader(Path(request.app.state.settings.metrics_db_path)),
        game_repo=request.app.state.game_repo,
        game_server=request.app.state.game_server,
    )
    return render_page(
        request,
        template_name="monitoring.html",
        context={
            "username": request.user.username,
            "range_choices": _range_choices(selected, translate=translate),
            "summary": page.games,
            "completed_durations": _completed_durations(page.games, translate=translate),
            "live_status": page.live_status,
            "chart_groups": _chart_groups(page.charts, translate=translate),
            "last_backup_age": None
            if page.last_backup_age_seconds is None
            else format_duration_seconds(page.last_backup_age_seconds, translate=translate),
            "plot_width": PLOT_WIDTH,
            "plot_height": PLOT_HEIGHT,
        },
    )
