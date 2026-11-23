from __future__ import annotations

from operator import attrgetter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.dal.models import TournamentGame


def current_games(games: list[TournamentGame]) -> list[dict[str, object]]:
    """
    Return the games still being played, in the given order, each with its players East to North.
    """
    return [
        {"game_id": game.game_id, "players": game.players, "started_at": game.created_at}
        for game in games
        if game.ended_at is None
    ]


def played_games(games: list[TournamentGame]) -> list[dict[str, object]]:
    """
    Return the games that have ended, latest end first, each shaped as its ``game_ended`` event with its ``ended_at``.
    """
    ended = sorted((game for game in games if game.ended_at is not None), key=attrgetter("ended_at"), reverse=True)
    return [
        {
            "game_id": game.game_id,
            "players": game.players,
            "ended_at": game.ended_at,
            "end_reason": game.end_reason,
            "result": [standing.model_dump(mode="json", exclude={"user_id"}) for standing in game.result or []],
        }
        for game in ended
    ]
