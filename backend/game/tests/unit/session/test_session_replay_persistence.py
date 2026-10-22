from unittest.mock import MagicMock

from game.logic.events import (
    DiscardEvent,
    GameEndedEvent,
    ServiceEvent,
)
from game.logic.types import PlayerStanding
from game.session.manager import SessionManager
from game.session.models import PlayerSpec
from game.session.replay_collector import ReplayCollector
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.mocks import MOCK_AWAITING, MOCK_GAME_OVER, FakeGameRepository, MockConnection, MockGameService

from .helpers import make_game_with_player


def _make_manager_with_collector() -> tuple[SessionManager, MagicMock, MockGameService]:
    game_service = MockGameService()
    collector = MagicMock(spec=ReplayCollector)
    manager = SessionManager(game_service, replay_collector=collector, game_repository=FakeGameRepository())
    return manager, collector, game_service


def _make_game_end_event() -> ServiceEvent:
    return ServiceEvent(
        data=GameEndedEvent(
            winner_seat=0,
            standings=[
                PlayerStanding(
                    seat=0,
                    score=25000,
                    final_score=0,
                ),
            ],
        ),
    )


def _make_discard_event() -> ServiceEvent:
    return ServiceEvent(
        data=DiscardEvent(seat=0, tile_id=10),
    )


async def _create_started_game_with_collector(
    manager: SessionManager,
    game_id: str = "game1",
) -> list[MockConnection]:
    ticket = make_test_game_ticket(username="Alice", room_id=game_id, user_id="user-0")
    specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
    manager.create_pending_game(game_id=game_id, player_specs=specs)

    conn = MockConnection()
    manager.register_connection(conn)
    await manager.join_game(conn, game_id=game_id, session_token=ticket)
    conn._outbox.clear()
    return [conn]


class TestReplayCollectorMerge:
    def test_replay_collector_merge__when_no_payloads__should_return_empty_json(self):
        result = ReplayCollector._merge_round_started_payloads([])
        assert result == "{}"


class TestSessionReplayStart:
    async def test_replay_start__when_game_starts__should_start_collector_with_seed(self):
        manager, collector, game_service = _make_manager_with_collector()
        await _create_started_game_with_collector(manager)

        seed = game_service.get_game_seed("game1")
        collector.start_game.assert_called_once_with(game_id="game1", seed=seed, rng_version="pcg64dxsm-v1")


class TestSessionReplayCollect:
    async def test_replay_collect__when_events_broadcast__should_collect_them(self):
        manager, collector, _game_service = _make_manager_with_collector()
        game, _player, _conn = make_game_with_player(manager)

        events = [_make_discard_event()]
        await manager._broadcast_events(game, events, MOCK_AWAITING)
        collector.collect_events.assert_called_once_with("game1", events)


class TestSessionReplaySave:
    async def test_replay_save__when_game_end_event__should_save_and_cleanup(self):
        manager, collector, _game_service = _make_manager_with_collector()
        game, _player, _conn = make_game_with_player(manager)

        events = [_make_game_end_event()]
        await manager._broadcast_events(game, events, MOCK_GAME_OVER)
        collector.save.assert_awaited_once_with("game1", collector.detach_game.return_value)

    async def test_replay_save__when_no_game_end_event__should_not_save(self):
        manager, collector, _game_service = _make_manager_with_collector()
        game, _player, _conn = make_game_with_player(manager)

        events = [_make_discard_event()]
        await manager._broadcast_events(game, events, MOCK_AWAITING)
        collector.save.assert_not_called()


class TestSessionReplayCleanup:
    async def test_replay_cleanup__when_game_abandoned__should_cleanup_collector(self):
        manager, collector, _game_service = _make_manager_with_collector()
        conns = await _create_started_game_with_collector(manager)

        # leave the game, making it empty -- should trigger cleanup
        await manager.leave_game(conns[0])
        collector.cleanup_game.assert_called_once_with("game1")

    async def test_replay_cleanup__when_no_collector_on_abandon__should_not_raise(self):
        game_service = MockGameService()
        manager = SessionManager(game_service, game_repository=FakeGameRepository())

        ticket = make_test_game_ticket(username="Alice", room_id="game1", user_id="user-0")
        specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
        manager.create_pending_game(game_id="game1", player_specs=specs)
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, game_id="game1", session_token=ticket)

        await manager.leave_game(conn)  # should not raise
