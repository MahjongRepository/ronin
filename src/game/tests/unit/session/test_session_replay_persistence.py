from unittest.mock import MagicMock

from game.logic.events import (
    BroadcastTarget,
    DiscardEvent,
    EventType,
    GameEndedEvent,
    ServiceEvent,
)
from game.logic.types import PlayerStanding
from game.session.manager import SessionManager
from game.session.replay_collector import ReplayCollector
from game.tests.mocks import MockConnection, MockGameService

from .helpers import make_game_with_player


def _make_manager_with_collector() -> tuple[SessionManager, MagicMock, MockGameService]:
    """Create a SessionManager with a mock ReplayCollector."""
    game_service = MockGameService()
    collector = MagicMock(spec=ReplayCollector)
    manager = SessionManager(game_service, replay_collector=collector)
    return manager, collector, game_service


def _make_game_end_event() -> ServiceEvent:
    return ServiceEvent(
        event=EventType.GAME_END,
        data=GameEndedEvent(
            target="all",
            winner_seat=0,
            standings=[
                PlayerStanding(
                    seat=0,
                    score=25000,
                    final_score=0,
                ),
            ],
        ),
        target=BroadcastTarget(),
    )


def _make_discard_event() -> ServiceEvent:
    return ServiceEvent(
        event=EventType.DISCARD,
        data=DiscardEvent(seat=0, tile_id=10),
        target=BroadcastTarget(),
    )


async def _create_started_game_with_collector(
    manager: SessionManager,
    game_id: str = "game1",
) -> list[MockConnection]:
    """Create a started game through the room flow for replay tests."""
    manager.create_room(game_id, num_ai_players=3)
    conn = MockConnection()
    manager.register_connection(conn)
    await manager.join_room(conn, game_id, "Alice", "tok-alice")
    await manager.set_ready(conn, ready=True)
    conn._outbox.clear()
    return [conn]


class TestSessionReplayStart:
    """Tests for replay collector start_game trigger when game starts."""

    async def test_start_game_calls_collector_start_with_seed(self):
        """Replay collector start_game is called with game_id and seed when game starts."""
        manager, collector, game_service = _make_manager_with_collector()
        await _create_started_game_with_collector(manager)

        seed = game_service.get_game_seed("game1")
        collector.start_game.assert_called_once_with("game1", seed, "pcg64dxsm-v1")

    def test_create_room_does_not_call_collector_start(self):
        """Replay collector start_game is NOT called during create_room (seed not yet known)."""
        manager, collector, _game_service = _make_manager_with_collector()
        manager.create_room("game1", num_ai_players=3)
        collector.start_game.assert_not_called()

    def test_create_room_without_collector(self):
        """No error when replay collector is not configured."""
        game_service = MockGameService()
        manager = SessionManager(game_service)
        manager.create_room("game1")  # should not raise


class TestSessionReplayCollect:
    """Tests for replay collector collect_events trigger in _broadcast_events."""

    async def test_broadcast_events_calls_collect(self):
        manager, collector, _game_service = _make_manager_with_collector()
        game, _player, _conn = make_game_with_player(manager)

        events = [_make_discard_event()]
        await manager._broadcast_events(game, events)

        collector.collect_events.assert_called_once_with("game1", events)

    async def test_broadcast_without_collector(self):
        """No error when broadcasting without a replay collector."""
        game_service = MockGameService()
        manager = SessionManager(game_service)
        game, _player, _conn = make_game_with_player(manager)

        events = [_make_discard_event()]
        await manager._broadcast_events(game, events)  # should not raise


class TestSessionReplaySave:
    """Tests for replay collector save_and_cleanup trigger on GameEndedEvent."""

    async def test_game_end_calls_save_and_cleanup(self):
        manager, collector, _game_service = _make_manager_with_collector()
        game, _player, _conn = make_game_with_player(manager)

        events = [_make_game_end_event()]
        await manager._close_connections_on_game_end(game, events)

        collector.save_and_cleanup.assert_awaited_once_with("game1")

    async def test_no_save_without_game_end_event(self):
        manager, collector, _game_service = _make_manager_with_collector()
        game, _player, _conn = make_game_with_player(manager)

        events = [_make_discard_event()]
        await manager._close_connections_on_game_end(game, events)

        collector.save_and_cleanup.assert_not_called()

    async def test_game_end_without_collector(self):
        """No error when game ends without a replay collector."""
        game_service = MockGameService()
        manager = SessionManager(game_service)
        game, _player, _conn = make_game_with_player(manager)

        events = [_make_game_end_event()]
        await manager._close_connections_on_game_end(game, events)  # should not raise


class TestSessionReplayCleanup:
    """Tests for replay collector cleanup_game trigger on abandoned game."""

    async def test_abandoned_game_calls_cleanup(self):
        manager, collector, _game_service = _make_manager_with_collector()
        conns = await _create_started_game_with_collector(manager)

        # leave the game, making it empty -- should trigger cleanup
        await manager.leave_game(conns[0])

        collector.cleanup_game.assert_called_once_with("game1")

    async def test_abandoned_game_without_collector(self):
        """No error when game is abandoned without a replay collector."""
        game_service = MockGameService()
        manager = SessionManager(game_service)

        manager.create_room("game1", num_ai_players=3)
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "game1", "Alice", "tok-alice")
        await manager.set_ready(conn, ready=True)

        await manager.leave_game(conn)  # should not raise
