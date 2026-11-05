from __future__ import annotations

import functools
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from lobby.game_transition import fetch_game_server_status
from lobby.views.assets import render_page, translate_for_request
from lobby.views.history_handlers import format_duration_seconds
from lobby.views.monitoring_ranges import DEFAULT_MONITORING_RANGE, MonitoringRange

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

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


async def monitoring_page(request: Request) -> Response:
    """
    GET /admin/monitoring - render the admin monitoring page: live games now and the games started in ``?range=``.
    """
    translate = functools.partial(translate_for_request, request)
    selected = _selected_range(request)
    summary = await request.app.state.game_repo.get_games_summary(since=datetime.now(UTC) - selected.duration)
    live_status = await fetch_game_server_status(game_server=request.app.state.game_server)
    return render_page(
        request,
        template_name="monitoring.html",
        context={
            "username": request.user.username,
            "range_choices": _range_choices(selected, translate=translate),
            "summary": summary,
            "completed_durations": _completed_durations(summary, translate=translate),
            "live_status": live_status,
        },
    )
