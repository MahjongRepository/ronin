from unittest.mock import AsyncMock


class MockGameRepository:
    def __init__(self) -> None:
        self.games: dict[str, dict] = {}
        self.stored_games: dict[str, object] = {}
        self.create_game = AsyncMock(side_effect=self._create_game)
        self.finish_game = AsyncMock(side_effect=self._finish_game)
        self.get_game = AsyncMock(side_effect=self._get_game)

    async def _create_game(self, game):
        self.stored_games[game.game_id] = game
        self.games[game.game_id] = {
            "game_id": game.game_id,
            "started_at": game.started_at,
            "ended_at": None,
            "end_reason": None,
        }

    async def _finish_game(self, game_id, ended_at, end_reason, num_rounds_played=None, standings=None):
        if game_id in self.games and self.games[game_id]["ended_at"] is None:
            self.games[game_id]["ended_at"] = ended_at
            self.games[game_id]["end_reason"] = end_reason
            self.games[game_id]["num_rounds_played"] = num_rounds_played
            self.games[game_id]["standings"] = standings

    async def _get_game(self, game_id):
        return self.stored_games.get(game_id)
