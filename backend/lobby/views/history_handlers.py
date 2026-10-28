from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lobby.views.assets import render_page, translate_for_request

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from starlette.requests import Request
    from starlette.responses import Response

    from shared.dal.models import PlayedGame

SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60
HISTORY_GAMES_LIMIT = 20


type Translate = Callable[..., str]


@dataclass(frozen=True)
class _GameTypeLabel:
    wind: str
    name: str


_GAME_TYPE_NAME_KEYS = {
    "hanchan": ("南", "history.game_type.hanchan"),
    "tonpusen": ("東", "history.game_type.tonpusen"),
}


def _format_duration(started_at: datetime, ended_at: datetime, *, translate: Translate) -> str:
    """
    Format game duration in the page's language, e.g. '5m 30s', '1h 12m' or '45s' in English.
    """
    seconds = max(int((ended_at - started_at).total_seconds()), 0)
    if seconds >= SECONDS_PER_HOUR:
        hours = seconds // SECONDS_PER_HOUR
        minutes = (seconds % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE
        return translate("history.duration.hours", hours=hours, minutes=minutes)

    if seconds >= SECONDS_PER_MINUTE:
        minutes = seconds // SECONDS_PER_MINUTE
        return translate("history.duration.minutes", minutes=minutes, seconds=seconds % SECONDS_PER_MINUTE)

    return translate("history.duration.seconds", seconds=seconds)


def _game_type_label(game_type: str, *, translate: Translate) -> _GameTypeLabel | None:
    """
    Return the wind glyph and the localized name of a game type, or None for a type the history cannot name.
    """
    known = _GAME_TYPE_NAME_KEYS.get(game_type)
    if known is None:
        return None

    wind, name_key = known
    return _GameTypeLabel(wind=wind, name=translate(name_key))


def _build_replay_url(game_id: str, seat: int | None = None) -> str:
    """
    Build the replay page link, opening from `seat` when one is given.
    """
    replay_url = f"/play/history/{game_id}"
    if seat is None:
        return replay_url

    return f"{replay_url}?seat={seat}"


def _prepare_history_for_display(games: list[PlayedGame], user_id: str, *, translate: Translate) -> list[dict]:
    """
    Transform played games into template-friendly view models.

    A game the viewer played links its replay from their seat; the shareable link never carries one.
    """
    result = []
    for game in games:
        has_scores = game.standings and game.standings[0].final_score is not None
        viewer_seat = None
        players = []
        for i, s in enumerate(game.standings):
            is_viewer = s.user_id == user_id
            if is_viewer:
                viewer_seat = s.seat

            players.append(
                {
                    "name": s.name,
                    "score": s.score,
                    "final_score": s.final_score,
                    "is_winner": has_scores and i == 0,
                    "is_viewer": is_viewer,
                },
            )

        duration_label = None
        if game.ended_at:
            duration_label = _format_duration(game.started_at, game.ended_at, translate=translate)

        result.append(
            {
                "game": game,
                "players": players,
                "duration_label": duration_label,
                "game_type": _game_type_label(game.game_type, translate=translate),
                "replay_url": _build_replay_url(game.game_id),
                "viewer_replay_url": _build_replay_url(game.game_id, viewer_seat),
            },
        )

    return result


async def history_page(request: Request) -> Response:
    """
    GET /history - render the most recent completed games, newest first.
    """
    game_repo = request.app.state.game_repo
    games = await game_repo.get_recent_completed_games(limit=HISTORY_GAMES_LIMIT)
    display_games = _prepare_history_for_display(
        games, request.user.user_id, translate=functools.partial(translate_for_request, request)
    )
    return render_page(
        request,
        template_name="history.html",
        context={"games": display_games, "username": request.user.username},
    )
