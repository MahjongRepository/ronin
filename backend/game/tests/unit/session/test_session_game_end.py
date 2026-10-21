import logging
from unittest.mock import AsyncMock, MagicMock

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import BroadcastTarget, EventType, GameEndedEvent, ServiceEvent
from game.logic.exceptions import InvalidGameActionError
from game.logic.types import PlayerStanding
from game.messaging.types import SessionErrorCode
from game.session import heartbeat as heartbeat_module
from game.session.manager import SessionManager
from game.session.models import Player, PlayerSpec
from game.session.replay_collector import ReplayCollector
from game.tests.mocks import MockConnection, MockGameRepository, MockGameService, MockResultEvent
from shared.dal.models import GameEndReason
from shared.storage import LocalReplayStorage, replay_file_path

from .helpers import (
    arrange_final_discard,
    create_started_game,
    fire_turn_timer_now,
    make_game_with_player,
    run_timeout,
    wait_for_background_tasks,
)


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


class TestSessionManagerGameEnd:
    def _make_game_end_event(self) -> ServiceEvent:
        return ServiceEvent(
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
        )

    async def test_game_end__when_game_end_event__should_close_connection_with_1000(self, manager):
        game, _player, conn = make_game_with_player(manager)

        events = [self._make_game_end_event()]
        await manager._close_connections_on_game_end(game, events)
        assert conn.is_closed is True
        assert conn._close_code == 1000
        assert conn._close_reason == "game_ended"

    async def test_game_end__when_events_lack_game_end__should_keep_connection_open(self, manager):
        game, _player, conn = make_game_with_player(manager)

        generic_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                player="Alice",
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target=BroadcastTarget(),
        )
        await manager._close_connections_on_game_end(game, [generic_event])
        assert conn.is_closed is False

    async def test_game_end__when_game_end_event_with_two_players__should_close_both(self, manager):
        game, _player, conn1 = make_game_with_player(manager)

        conn2 = MockConnection()
        player2 = Player(connection=conn2, name="Bob", session_token="tok-bob", game_id="game1", seat=1)
        game.players[conn2.connection_id] = player2

        events = [self._make_game_end_event()]
        await manager._close_connections_on_game_end(game, events)
        assert conn1.is_closed is True
        assert conn2.is_closed is True


class TestFailGame:
    async def test_fail_game__when_game_running__should_send_internal_error_record_error_and_close_with_1011(self):
        game_repo = MockGameRepository()
        manager = SessionManager(MockGameService(), game_repository=game_repo)
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        game = manager.get_game("game1")

        assert manager.fail_game(game, reason="engine fault", exc=RuntimeError("boom")) is True
        assert manager.fail_game(game, reason="engine fault again") is False
        assert game.ended is True
        assert manager.get_game("game1") is None
        assert "game1" not in manager._game_locks

        await wait_for_background_tasks(manager)
        for conn in conns:
            assert [m["code"] for m in conn.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
            assert conn._close_code == 1011
            assert conn._close_reason == "internal_error"

        assert game_repo.games["game1"]["end_reason"] == GameEndReason.ERROR
        assert game_repo.finish_game.await_count == 1

    async def test_fail_game__when_game_still_pending__should_close_joined_player_and_drop_pending_game(self):
        game_repo = MockGameRepository()
        manager = SessionManager(MockGameService(), game_repository=game_repo)
        manager.create_pending_game(
            game_id="game1",
            player_specs=[
                PlayerSpec(name="Alice", user_id="u0", game_ticket="ticket-0"),
                PlayerSpec(name="Bob", user_id="u1", game_ticket="ticket-1"),
            ],
            num_ai_players=2,
        )
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, game_id="game1", session_token="ticket-0")
        timeout_task = manager._pending_games["game1"].timeout_task

        manager.fail_game(manager.get_game("game1"), reason="join failed")
        await wait_for_background_tasks(manager)
        assert timeout_task.cancelled()
        assert manager.pending_game_count == 0
        assert manager._session_store.get_session("ticket-1") is None
        assert conn._close_code == 1011
        game_repo.finish_game.assert_not_called()

    async def test_fail_game__when_replay_save_and_a_send_fail__should_log_them_and_still_record_and_close_the_rest(
        self, caplog
    ):
        game_repo = MockGameRepository()
        collector = MagicMock(spec=ReplayCollector)
        collector.save_and_cleanup = AsyncMock(side_effect=KeyError("replay buffer"))
        manager = SessionManager(MockGameService(), replay_collector=collector, game_repository=game_repo)
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        conns[0].send_message = AsyncMock(side_effect=ValueError("encoder broke"))

        with caplog.at_level(logging.ERROR):
            manager.fail_game(manager.get_game("game1"), reason="engine fault")
            await wait_for_background_tasks(manager)

        assert [r.msg["event"] for r in caplog.records if r.levelno == logging.ERROR] == [
            "game failed",
            "failed to save the replay of a failed game",
            "failed to close a connection of a failed game",
        ]
        assert game_repo.games["game1"]["end_reason"] == GameEndReason.ERROR
        assert conns[0]._close_code == 1011
        assert conns[1]._close_code == 1011

    async def test_pending_game_timeout__when_game_start_raises__should_fail_the_game(self, short_pending_timeout):
        game_service = MockGameService()
        game_service.start_game = AsyncMock(side_effect=RuntimeError("start failed"))
        manager = SessionManager(game_service)
        manager.create_pending_game(
            game_id="game1",
            player_specs=[
                PlayerSpec(name="Alice", user_id="u0", game_ticket="ticket-0"),
                PlayerSpec(name="Bob", user_id="u1", game_ticket="ticket-1"),
            ],
            num_ai_players=2,
        )
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, game_id="game1", session_token="ticket-0")

        timeout_task = manager._pending_games["game1"].timeout_task
        assert timeout_task is not None

        await timeout_task
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert [m["code"] for m in conn.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
        assert conn._close_code == 1011

    async def test_heartbeat_loop__when_it_raises__should_fail_its_game(self, manager, monkeypatch):
        monkeypatch.setattr(heartbeat_module, "HEARTBEAT_CHECK_INTERVAL", 0)
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        heartbeat_task = manager._heartbeat._tasks["game:game1"]

        async def broken_check(*_args, **_kwargs):
            raise RuntimeError("heartbeat broke")

        monkeypatch.setattr(manager._heartbeat, "_close_stale_connections", broken_check)
        await heartbeat_task
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert [(c._close_code, c._close_reason) for c in conns] == [(1011, "internal_error"), (1011, "internal_error")]

    async def test_heartbeat__when_game_cleaned_up__should_stop_game_task(self, manager):
        conns = await create_started_game(
            manager,
            num_ai_players=0,
            player_names=["P0", "P1", "P2", "P3"],
        )
        assert "game:game1" in manager._heartbeat._tasks
        heartbeat_task = manager._heartbeat._tasks.get("game:game1")

        # leave all players -- game becomes empty, cleanup runs
        for c in conns:
            await manager.leave_game(c)

        assert "game:game1" not in manager._heartbeat._tasks
        assert heartbeat_task.done()


class TestGameEndFromAction:
    async def test_game_end__when_action_ends_game__should_close_all_connections(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = AsyncMock(return_value=_make_game_end_events())

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        assert conns[0].is_closed
        assert conns[0]._close_code == 1000
        assert conns[0]._close_reason == "game_ended"
        assert conns[1].is_closed

    async def test_game_end__when_ai_replacement_after_invalid_action_ends_game__should_close_remaining_with_1000(
        self, manager
    ):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            return_value=_make_game_end_events(),
        )
        error = InvalidGameActionError(action="discard", seat=0, reason="bad tile")
        manager._game_service.handle_action = AsyncMock(side_effect=error)

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        # Offender closed with 1008 (invalid action)
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008
        # Bob closed with 1000 (game ended via AI replacement)
        assert conns[1].is_closed
        assert conns[1]._close_code == 1000
        assert conns[1]._close_reason == "game_ended"


class TestGameEndFromTimeout:
    async def test_game_end__when_turn_timer_fires_on_final_discard__should_save_replay_record_finish_and_close(
        self, seeded_engine, tmp_path
    ):
        game_repo = MockGameRepository()
        manager = SessionManager(
            seeded_engine,
            replay_collector=ReplayCollector(LocalReplayStorage(tmp_path)),
            game_repository=game_repo,
        )
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_seat = manager._players[conns[0].connection_id].seat
        arrange_final_discard(seeded_engine, game_id="game1", seat=alice_seat)

        fired = fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await fired
        assert game_repo.games["game1"]["end_reason"] == GameEndReason.COMPLETED
        assert game_repo.games["game1"]["ended_at"] is not None
        assert replay_file_path(tmp_path, "game1").exists()
        assert [(c._close_code, c._close_reason) for c in conns] == [(1000, "game_ended"), (1000, "game_ended")]

    async def test_game_end__when_ai_replacement_after_timeout_ends_game__should_close_remaining_with_1000(
        self, manager
    ):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            return_value=_make_game_end_events(),
        )
        error = InvalidGameActionError(action="pass", seat=0, reason="resolution failed")
        manager._game_service.handle_timeout = AsyncMock(side_effect=error)

        await run_timeout(manager, game_id="game1", timeout_type=TimeoutType.MELD, seat=0)
        # Offender closed with 1008
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008
        # Bob closed with 1000 (game ended)
        assert conns[1].is_closed
        assert conns[1]._close_code == 1000


class TestGameEndFromLeaveGame:
    async def test_game_end__when_ai_replacement_after_leave_ends_game__should_close_remaining_with_1000(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            return_value=_make_game_end_events(),
        )

        await manager.leave_game(conns[0])
        # Bob's connection should be closed with game_ended
        assert conns[1].is_closed
        assert conns[1]._close_code == 1000
        assert conns[1]._close_reason == "game_ended"
