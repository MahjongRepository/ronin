from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from shared.dal.models import PlayedGame

HISTORY_GAMES_LIMIT = 20


_GAME_TYPE_WINDS = {
    "hanchan": "南",
    "tonpusen": "東",
}


def _as_utc(moment: datetime) -> datetime:
    """
    Return ``moment`` with an explicit offset, reading a stored value without one as UTC.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)

    return moment


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

        started_at = _as_utc(game.started_at)
        duration_seconds = None
        if game.ended_at:
            duration_seconds = (_as_utc(game.ended_at) - started_at).total_seconds()

        result.append(
            {
                "game_id": game.game_id,
                "started_at": started_at.isoformat(),
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
