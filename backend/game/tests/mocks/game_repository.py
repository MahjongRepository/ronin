from typing import TYPE_CHECKING

from shared.dal.game_repository import GameRepository
from shared.dal.models import GameEndReason, GamesSummary

if TYPE_CHECKING:
    from datetime import datetime

    from shared.dal.models import PlayedGame


class FakeGameRepository(GameRepository):
    def __init__(self) -> None:
        self.games: dict[str, PlayedGame] = {}
        self.finishes: list[PlayedGame] = []

    def create_game(self, game: PlayedGame) -> None:
        self.games.setdefault(game.game_id, game)

    def finish_game(self, game: PlayedGame) -> None:
        self.finishes.append(game)
        existing = self.games.get(game.game_id)
        if existing is None or existing.ended_at is None:
            self.games[game.game_id] = game

    async def get_recent_completed_games(self, limit: int = 20) -> list[PlayedGame]:
        completed = [game for game in self.games.values() if game.end_reason == GameEndReason.COMPLETED]
        return sorted(completed, key=lambda game: game.started_at, reverse=True)[:limit]

    async def get_game(self, game_id: str) -> PlayedGame | None:
        return self.games.get(game_id)

    async def get_games_summary(self, *, since: datetime) -> GamesSummary:
        return GamesSummary.from_timings(
            (game.end_reason, game.started_at, game.ended_at)
            for game in self.games.values()
            if game.started_at >= since
        )
