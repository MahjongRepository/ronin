from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import BroadcastTarget, EventType, GameEndedEvent, ServiceEvent
from game.logic.types import PlayerStanding
from game.session.manager import SessionManager
from game.tests.mocks import MockConnection, MockGameService

from .helpers import create_started_game


class MockGameRepository:
    """In-memory game repository for testing game history recording."""

    def __init__(self) -> None:
        self.games: dict[str, dict] = {}
        self.create_game = AsyncMock(side_effect=self._create_game)
        self.finish_game = AsyncMock(side_effect=self._finish_game)

    async def _create_game(self, game):
        self.games[game.game_id] = {
            "game_id": game.game_id,
            "started_at": game.started_at,
            "player_ids": game.player_ids,
            "ended_at": None,
            "end_reason": None,
        }

    async def _finish_game(self, game_id, ended_at, end_reason="completed"):
        if game_id in self.games and self.games[game_id]["ended_at"] is None:
            self.games[game_id]["ended_at"] = ended_at
            self.games[game_id]["end_reason"] = end_reason


@pytest.fixture
def game_repo():
    return MockGameRepository()


@pytest.fixture
def manager_with_repo(game_repo):
    game_service = MockGameService()
    return SessionManager(game_service, game_repository=game_repo)


def _make_game_end_events() -> list[ServiceEvent]:
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

    async def test_game_start_includes_player_ids(self, manager_with_repo, game_repo):
        """Player user_ids are captured in the PlayedGame record."""
        manager_with_repo.create_room("game1", num_ai_players=3)
        conn = MockConnection()
        manager_with_repo.register_connection(conn)
        await manager_with_repo.join_room(conn, "game1", "Alice", user_id="user-alice")
        await manager_with_repo.set_ready(conn, ready=True)

        game_repo.create_game.assert_called_once()
        recorded = game_repo.games["game1"]
        assert "user-alice" in recorded["player_ids"]

    async def test_game_start_skipped_without_repository(self, manager):
        """No error when game_repository is None (default)."""
        await create_started_game(manager, "game1")
        # just verify no exception was raised

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

    async def test_completed_game_has_ended_at(self, manager_with_repo, game_repo):
        conns = await create_started_game(
            manager_with_repo,
            "game1",
            num_ai_players=2,
            player_names=["Alice", "Bob"],
        )

        manager_with_repo._game_service.handle_action = AsyncMock(return_value=_make_game_end_events())
        await manager_with_repo.handle_game_action(conns[0], GameAction.DISCARD, {})

        recorded = game_repo.games["game1"]
        assert recorded["ended_at"] is not None
        assert recorded["end_reason"] == "completed"

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

    async def test_unstarted_game_not_recorded_as_abandoned(self, manager_with_repo, game_repo):
        """Pre-start games that get cleaned up are not recorded as abandoned."""
        manager_with_repo.create_room("game1", num_ai_players=3)
        conn = MockConnection()
        manager_with_repo.register_connection(conn)
        await manager_with_repo.join_room(conn, "game1", "Alice")

        # leave before the game starts
        await manager_with_repo.leave_room(conn)

        # finish_game should not have been called since game never started
        game_repo.finish_game.assert_not_called()

    async def test_abandon_db_failure_does_not_block_cleanup(self, manager_with_repo, game_repo):
        """DB failure during abandon recording does not prevent game cleanup."""
        conns = await create_started_game(manager_with_repo, "game1")

        game_repo.finish_game = AsyncMock(side_effect=RuntimeError("DB write failed"))
        await manager_with_repo.leave_game(conns[0])

        # game should still be cleaned up despite DB error
        assert manager_with_repo.get_game("game1") is None
