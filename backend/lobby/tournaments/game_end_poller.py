from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    from lobby.tournaments.hub import TournamentHub
    from shared.dal.game_repository import GameRepository
    from shared.dal.models import TournamentGame
    from shared.dal.tournament_repository import TournamentRepository

logger = structlog.get_logger()


class TournamentGameEndPoller:
    """
    Turn the finish the game server records in ``played_games`` into a tournament game's finish and ``game_ended``.

    The game server never calls the lobby, so the lobby polls the record of every unfinished tournament game it tracks:
    the games left unfinished when it starts, and each game the start handler adds. A game without a finish record stays
    tracked, never inferred as ended, however old. The ``tournament_games`` update is the dedup: only the pass that
    finishes the row publishes.
    """

    def __init__(
        self,
        *,
        tournament_repo: TournamentRepository,
        game_repo: GameRepository,
        hub: TournamentHub,
        interval_seconds: float,
    ) -> None:
        self._tournament_repo = tournament_repo
        self._game_repo = game_repo
        self._hub = hub
        self._interval_seconds = interval_seconds
        self._games: dict[str, TournamentGame] = {}
        self._task: asyncio.Task[None] | None = None

    def track(self, game: TournamentGame) -> None:
        """
        Watch a tournament game for its finish.
        """
        self._games[game.game_id] = game

    def untrack_tournament(self, tournament_id: str) -> None:
        """
        Stop watching every game of a tournament.
        """
        self._games = {game_id: game for game_id, game in self._games.items() if game.tournament_id != tournament_id}

    async def start(self) -> None:
        """
        Track the tournament games left unfinished, then start the polling task.
        """
        for game in await self._tournament_repo.list_unfinished_games():
            self.track(game)

        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """
        Cancel the polling task.
        """
        if self._task is not None:
            await cancel_and_wait([self._task])
            self._task = None

    async def poll_once(self) -> None:
        """
        Finish every tracked game whose ``played_games`` record has ended, publishing ``game_ended`` for each.

        The event names the players East to North as the tournament started them, and the result in the record's order:
        placement order for a completed game, seat order with no scores for an abandoned or failed one.
        """
        for game in list(self._games.values()):
            played = await self._game_repo.get_game(game.game_id)
            if played is None or played.ended_at is None or played.end_reason is None:
                continue

            finished = await self._tournament_repo.finish_game(
                game_id=game.game_id,
                ended_at=played.ended_at.timestamp(),
                end_reason=played.end_reason,
                result=played.standings,
            )
            self._games.pop(game.game_id, None)
            if not finished:
                continue

            self._hub.publish(
                game.tournament_id,
                {
                    "type": "game_ended",
                    "game_id": game.game_id,
                    "players": game.players,
                    "end_reason": played.end_reason,
                    "result": [standing.model_dump(mode="json", exclude={"user_id"}) for standing in played.standings],
                },
            )
            logger.info(
                "tournament game ended",
                tournament_id=game.tournament_id,
                game_id=game.game_id,
                end_reason=played.end_reason,
            )

    async def _poll_loop(self) -> None:
        """
        Run a pass every interval while any game is tracked; a failed pass is logged and the next one still runs.
        """
        while True:
            await asyncio.sleep(self._interval_seconds)
            if not self._games:
                continue

            try:
                await self.poll_once()
            except Exception:
                logger.exception("tournament game end poll failed")
