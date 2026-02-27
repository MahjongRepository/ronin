from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import BroadcastTarget, EventType, GameEndedEvent, ServiceEvent
from game.logic.types import PlayerStanding
from game.session.manager import SessionManager
from game.tests.mocks import MockGameService

from .helpers import create_started_game


class MockGameRepository:
    """In-memory game repository for testing game history recording."""

    def __init__(self) -> None:
        self.games: dict[str, dict] = {}
        self.stored_games: dict[str, object] = {}  # game_id -> PlayedGame
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

    async def _finish_game(self, game_id, ended_at, end_reason="completed", num_rounds_played=None, standings=None):
        if game_id in self.games and self.games[game_id]["ended_at"] is None:
            self.games[game_id]["ended_at"] = ended_at
            self.games[game_id]["end_reason"] = end_reason
            self.games[game_id]["num_rounds_played"] = num_rounds_played
            self.games[game_id]["standings"] = standings

    async def _get_game(self, game_id):
        return self.stored_games.get(game_id)


@pytest.fixture
def game_repo():
    return MockGameRepository()


@pytest.fixture
def manager_with_repo(game_repo):
    game_service = MockGameService()
    return SessionManager(game_service, game_repository=game_repo)


def _make_game_end_events(*, num_rounds: int = 1) -> list[ServiceEvent]:
    return [
        ServiceEvent(
            event=EventType.GAME_END,
            data=GameEndedEvent(
                type=EventType.GAME_END,
                target="all",
                winner_seat=0,
                standings=[
                    PlayerStanding(seat=0, score=25000, final_score=0),
                ],
                num_rounds=num_rounds,
            ),
            target=BroadcastTarget(),
        ),
    ]


class TestGameStartRecording:
    """Verify game start is persisted when a game starts successfully."""

    async def test_game_start_recorded(self, manager_with_repo, game_repo):
        await create_started_game(manager_with_repo, "game1")

        game_repo.create_game.assert_called_once()
        recorded = game_repo.games["game1"]
        assert recorded["game_id"] == "game1"
        assert isinstance(recorded["started_at"], datetime)
        assert recorded["ended_at"] is None

    async def test_game_start_populates_standings_with_player_info(self, manager_with_repo, game_repo):
        """Standings at game start carry names, seats, and user_ids for all players."""
        await create_started_game(
            manager_with_repo,
            "game1",
            num_ai_players=2,
            player_names=["Alice", "Bob"],
        )

        played_game = game_repo.stored_games["game1"]
        assert len(played_game.standings) == 4
        # Humans get user_ids from the pending-game player_specs
        assert played_game.standings[0].name == "Alice"
        assert played_game.standings[0].seat == 0
        assert played_game.standings[0].user_id == "user-0"
        assert played_game.standings[1].name == "Bob"
        assert played_game.standings[1].seat == 1
        assert played_game.standings[1].user_id == "user-1"
        # AI players have empty user_id
        assert played_game.standings[2].name == "AI"
        assert played_game.standings[2].user_id == ""
        assert played_game.standings[3].name == "AI"
        assert played_game.standings[3].user_id == ""
        # No scores at game start
        assert all(s.score is None for s in played_game.standings)

    async def test_game_start_records_game_type(self, manager_with_repo, game_repo):
        """Game type from settings is persisted at game start."""
        await create_started_game(manager_with_repo, "game1")

        played_game = game_repo.stored_games["game1"]
        assert played_game.game_type == "hanchan"

    async def test_game_start_skipped_without_repository(self, manager):
        """No error when game_repository is None (default)."""
        await create_started_game(manager, "game1")
        # just verify no exception was raised

    async def test_game_start_skipped_when_game_state_missing(self, manager_with_repo, game_repo):
        """When game state is unavailable, _record_game_start is a no-op."""
        manager_with_repo._game_service.get_game_state = lambda _: None
        await create_started_game(manager_with_repo, "game1")
        game_repo.create_game.assert_not_called()

    async def test_game_start_db_failure_does_not_block(self, manager_with_repo, game_repo):
        """DB failure during game start recording does not prevent the game from starting."""
        game_repo.create_game = AsyncMock(side_effect=RuntimeError("DB write failed"))

        await create_started_game(manager_with_repo, "game1")

        # game should still be running despite the DB error
        game = manager_with_repo.get_game("game1")
        assert game is not None
        assert game.started


class TestGameCompletionRecording:
    """Verify completed games are recorded with end_reason='completed'."""

    async def test_completed_game_recorded(self, manager_with_repo, game_repo):
        conns = await create_started_game(
            manager_with_repo,
            "game1",
            num_ai_players=2,
            player_names=["Alice", "Bob"],
        )

        manager_with_repo._game_service.handle_action = AsyncMock(return_value=_make_game_end_events())
        await manager_with_repo.handle_game_action(conns[0], GameAction.DISCARD, {})

        game_repo.finish_game.assert_called_once()
        call_args = game_repo.finish_game.call_args
        assert call_args[0][0] == "game1"
        assert isinstance(call_args.kwargs["ended_at"], datetime)
        assert call_args.kwargs["end_reason"] == "completed"

    async def test_completed_game_passes_standings_from_event(self, manager_with_repo, game_repo):
        """GameEndedEvent standings (scores, placement order) are forwarded to finish_game."""
        conns = await create_started_game(
            manager_with_repo,
            "game1",
            num_ai_players=2,
            player_names=["Alice", "Bob"],
        )

        events = [
            ServiceEvent(
                event=EventType.GAME_END,
                data=GameEndedEvent(
                    type=EventType.GAME_END,
                    target="all",
                    winner_seat=1,
                    standings=[
                        PlayerStanding(seat=1, score=40000, final_score=50),
                        PlayerStanding(seat=0, score=25000, final_score=0),
                        PlayerStanding(seat=2, score=20000, final_score=-15),
                        PlayerStanding(seat=3, score=15000, final_score=-35),
                    ],
                    num_rounds=8,
                ),
                target=BroadcastTarget(),
            ),
        ]
        manager_with_repo._game_service.handle_action = AsyncMock(return_value=events)
        await manager_with_repo.handle_game_action(conns[0], GameAction.DISCARD, {})

        call_kwargs = game_repo.finish_game.call_args.kwargs
        standings = call_kwargs["standings"]
        assert len(standings) == 4
        # Winner (seat 1, Bob) is first in placement order
        assert standings[0].name == "Bob"
        assert standings[0].seat == 1
        assert standings[0].user_id == "user-1"
        assert standings[0].score == 40000
        assert standings[0].final_score == 50
        # Second place (seat 0, Alice)
        assert standings[1].name == "Alice"
        assert standings[1].seat == 0
        assert standings[1].user_id == "user-0"
        # AI players have empty user_id
        assert standings[2].name == "AI"
        assert standings[2].seat == 2
        assert standings[2].user_id == ""
        assert standings[3].name == "AI"
        assert standings[3].seat == 3
        assert standings[3].user_id == ""

    async def test_completed_game_records_round_count(self, manager_with_repo, game_repo):
        """num_rounds_played is taken from GameEndedEvent.num_rounds."""
        conns = await create_started_game(
            manager_with_repo,
            "game1",
            num_ai_players=2,
            player_names=["Alice", "Bob"],
        )

        manager_with_repo._game_service.handle_action = AsyncMock(
            return_value=_make_game_end_events(num_rounds=8),
        )
        await manager_with_repo.handle_game_action(conns[0], GameAction.DISCARD, {})

        call_kwargs = game_repo.finish_game.call_args.kwargs
        assert call_kwargs["num_rounds_played"] == 8

    async def test_completion_from_timeout(self, manager_with_repo, game_repo):
        """Game end triggered by timeout also records completion."""
        await create_started_game(
            manager_with_repo,
            "game1",
            num_ai_players=2,
            player_names=["Alice", "Bob"],
        )

        manager_with_repo._game_service.handle_timeout = AsyncMock(return_value=_make_game_end_events())
        await manager_with_repo._handle_timeout("game1", TimeoutType.TURN, 0)

        recorded = game_repo.games["game1"]
        assert recorded["end_reason"] == "completed"

    async def test_completion_db_failure_does_not_block_cleanup(self, manager_with_repo, game_repo):
        """DB failure during game completion recording does not prevent socket cleanup."""
        conns = await create_started_game(
            manager_with_repo,
            "game1",
            num_ai_players=2,
            player_names=["Alice", "Bob"],
        )

        game_repo.finish_game = AsyncMock(side_effect=RuntimeError("DB write failed"))
        manager_with_repo._game_service.handle_action = AsyncMock(return_value=_make_game_end_events())

        await manager_with_repo.handle_game_action(conns[0], GameAction.DISCARD, {})

        # connections should still be closed despite the DB error
        assert conns[0].is_closed
        assert conns[1].is_closed

    async def test_get_game_failure_does_not_block_socket_close(self, manager_with_repo, game_repo):
        """If get_game raises inside _record_game_finish, sockets still close."""
        conns = await create_started_game(
            manager_with_repo,
            "game1",
            num_ai_players=2,
            player_names=["Alice", "Bob"],
        )

        game_repo.get_game = AsyncMock(side_effect=RuntimeError("DB read failed"))
        manager_with_repo._game_service.handle_action = AsyncMock(return_value=_make_game_end_events())

        await manager_with_repo.handle_game_action(conns[0], GameAction.DISCARD, {})

        assert conns[0].is_closed
        assert conns[1].is_closed


class TestGameAbandonmentRecording:
    """Verify abandoned games are recorded with end_reason='abandoned'."""

    async def test_abandoned_game_recorded_when_all_leave(self, manager_with_repo, game_repo):
        """When all players leave a started game, it is recorded as abandoned."""
        conns = await create_started_game(manager_with_repo, "game1")

        await manager_with_repo.leave_game(conns[0])

        recorded = game_repo.games["game1"]
        assert recorded["end_reason"] == "abandoned"
        assert recorded["ended_at"] is not None

    async def test_completed_game_not_overwritten_by_abandon(self, manager_with_repo, game_repo):
        """A game already marked as completed does not trigger a second finish_game call."""
        conns = await create_started_game(
            manager_with_repo,
            "game1",
            num_ai_players=2,
            player_names=["Alice", "Bob"],
        )

        manager_with_repo._game_service.handle_action = AsyncMock(return_value=_make_game_end_events())
        await manager_with_repo.handle_game_action(conns[0], GameAction.DISCARD, {})

        # finish_game should be called exactly once with "completed".
        # The cleanup path (_cleanup_empty_game) must skip the "abandoned" call
        # because game.ended is already True.
        game_repo.finish_game.assert_called_once()
        recorded = game_repo.games["game1"]
        assert recorded["end_reason"] == "completed"

    async def test_abandon_db_failure_does_not_block_cleanup(self, manager_with_repo, game_repo):
        """DB failure during abandon recording does not prevent game cleanup."""
        conns = await create_started_game(manager_with_repo, "game1")

        game_repo.finish_game = AsyncMock(side_effect=RuntimeError("DB write failed"))
        await manager_with_repo.leave_game(conns[0])

        # game should still be cleaned up despite DB error
        assert manager_with_repo.get_game("game1") is None
