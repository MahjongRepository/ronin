from __future__ import annotations

import functools
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from lobby.game_transition import fetch_game_server_status
from lobby.views.assets import render_page, translate_for_request
from lobby.views.history_handlers import format_duration_seconds

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.views.history_handlers import Translate
    from shared.dal.models import GamesSummary

_RANGES: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}
_DEFAULT_RANGE = "24h"
_RANGE_LABEL_KEYS = {
    "1h": "monitoring.range.1h",
    "24h": "monitoring.range.24h",
    "7d": "monitoring.range.7d",
    "30d": "monitoring.range.30d",
    "90d": "monitoring.range.90d",
}


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


def _selected_range(request: Request) -> str:
    """
    Return the page's range from ``?range=``, the default for a missing or unknown one.
    """
    requested = request.query_params.get("range", _DEFAULT_RANGE)
    return requested if requested in _RANGES else _DEFAULT_RANGE


def _range_choices(selected: str, *, translate: Translate) -> list[_RangeChoice]:
    return [
        _RangeChoice(url=f"?range={name}", label=translate(_RANGE_LABEL_KEYS[name]), is_current=name == selected)
        for name in _RANGES
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
    summary = await request.app.state.game_repo.get_games_summary(since=datetime.now(UTC) - _RANGES[selected])
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
