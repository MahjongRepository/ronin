from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from shared.dal.models import PlayedGame

SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60
HISTORY_GAMES_LIMIT = 20


type Translate = Callable[..., str]


_GAME_TYPE_WINDS = {
    "hanchan": "南",
    "tonpusen": "東",
}


def format_duration_seconds(duration_seconds: float, *, translate: Translate) -> str:
    """
    Format a duration in whole seconds in the page's language, e.g. '5m 30s', '1h 12m' or '45s' in English.
    """
    seconds = max(int(duration_seconds), 0)
    if seconds >= SECONDS_PER_HOUR:
        hours = seconds // SECONDS_PER_HOUR
        minutes = (seconds % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE
        return translate("history.duration.hours", hours=hours, minutes=minutes)

    if seconds >= SECONDS_PER_MINUTE:
        minutes = seconds // SECONDS_PER_MINUTE
        return translate("history.duration.minutes", minutes=minutes, seconds=seconds % SECONDS_PER_MINUTE)

    return translate("history.duration.seconds", seconds=seconds)


def _build_replay_url(game_id: str, seat: int | None = None) -> str:
    """
    Build the replay page link, opening from `seat` when one is given.
    """
    replay_url = f"/play/history/{game_id}"
    if seat is None:
        return replay_url

    return f"{replay_url}?seat={seat}"


def history_entries(games: list[PlayedGame], user_id: str) -> list[dict]:
    """
    Turn played games into the history view's JSON entries, standings in their stored order.

    A game the viewer played links its replay from their seat; the shareable link never carries one. The wind is the
    game type's glyph, or None for a type the history cannot name.
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

        duration_seconds = None
        if game.ended_at:
            duration_seconds = (game.ended_at - game.started_at).total_seconds()

        result.append(
            {
                "game_id": game.game_id,
                "started_at": game.started_at.isoformat(),
                "num_rounds_played": game.num_rounds_played,
                "duration_seconds": duration_seconds,
                "game_type": game.game_type,
                "wind": _GAME_TYPE_WINDS.get(game.game_type),
                "players": players,
                "replay_url": _build_replay_url(game.game_id),
                "viewer_replay_url": _build_replay_url(game.game_id, viewer_seat),
            },
        )

    return result
