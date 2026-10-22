import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from mahjong.tile import TilesConverter

from game.logic.ai_player import AIPlayer
from game.logic.enums import GameAction
from game.logic.events import BroadcastTarget, EventType, GameEndedEvent, ServiceEvent
from game.logic.exceptions import InvalidGameActionError, ScoringError
from game.logic.scoring import HandResult
from game.logic.types import PlayerStanding
from game.messaging.encoder import decode
from game.messaging.types import SessionErrorCode
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.session import heartbeat as heartbeat_module
from game.session.manager import SessionManager
from game.session.models import Player, PlayerSpec
from game.session.replay_collector import ReplayCollector
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.mocks import MockConnection, MockGameRepository, MockGameService, MockResultEvent
from game.tests.unit.helpers import _update_player, _update_round_state
from game.wire.events import EVENT_TYPE_INT
from shared.dal.models import GameEndReason
from shared.storage import LocalReplayStorage, replay_file_path

from .helpers import (
    arrange_final_discard,
    create_started_game,
    fire_turn_timer_now,
    make_game_with_player,
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
        await manager._broadcast_events(game, events)
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
        await manager._broadcast_events(game, [generic_event])
        assert conn.is_closed is False

    async def test_game_end__when_game_end_event_with_two_players__should_close_both(self, manager):
        game, _player, conn1 = make_game_with_player(manager)

        conn2 = MockConnection()
        player2 = Player(connection=conn2, name="Bob", session_token="tok-bob", game_id="game1", seat=1)
        game.players[conn2.connection_id] = player2

        events = [self._make_game_end_event()]
        await manager._broadcast_events(game, events)
        assert conn1.is_closed is True
        assert conn2.is_closed is True


class TestFailGame:
    async def test_fail_game__when_game_running__should_send_internal_error_record_error_and_close_with_1011(self):
        game_repo = MockGameRepository()
        manager = SessionManager(MockGameService(), game_repository=game_repo)
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
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
        collector.save = AsyncMock(side_effect=KeyError("replay buffer"))
        manager = SessionManager(MockGameService(), replay_collector=collector, game_repository=game_repo)
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
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
        game_service.start_game = MagicMock(side_effect=RuntimeError("start failed"))
        manager = SessionManager(game_service)
        manager.create_pending_game(
            game_id="game1",
            player_specs=[
                PlayerSpec(name="Alice", user_id="u0", game_ticket="ticket-0"),
                PlayerSpec(name="Bob", user_id="u1", game_ticket="ticket-1"),
            ],
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

    async def test_game_action__when_the_scoring_library_fails_on_tsumo__should_fail_the_game_with_that_error(
        self, seeded_engine, caplog
    ):
        manager = SessionManager(seeded_engine)
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        conns = await create_started_game(manager, player_names=["Alice"])
        alice_seat = manager._players[conns[0].connection_id].seat
        winning_hand = tuple(TilesConverter.string_to_136_array(man="123456789", pin="12355"))
        _update_player(seeded_engine, game_id="game1", seat=alice_seat, tiles=winning_hand)
        _update_round_state(seeded_engine, "game1", current_player_seat=alice_seat, pending_call_prompt=None)

        with (
            patch("game.logic.turn.calculate_hand_value", return_value=HandResult(error="library failure")),
            caplog.at_level(logging.ERROR),
        ):
            await router.handle_message(
                conns[0], {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DECLARE_TSUMO}
            )
            await wait_for_background_tasks(manager)

        failure = next(r.msg for r in caplog.records if r.msg["event"] == "game failed")
        assert failure["reason"] == "game action failed"
        assert isinstance(failure["exc_info"], ScoringError)
        assert manager.get_game("game1") is None
        assert (conns[0]._close_code, conns[0]._close_reason) == (1011, "internal_error")

    async def test_game_action__when_an_ai_turn_after_the_committed_discard_is_refused__should_fail_the_game(
        self, seeded_engine, monkeypatch
    ):
        manager = SessionManager(seeded_engine)
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        conns = await create_started_game(manager, player_names=["Alice"])
        alice_seat = manager._players[conns[0].connection_id].seat
        round_state = seeded_engine.get_game_state("game1").round_state
        assert round_state.current_player_seat == alice_seat
        assert round_state.pending_call_prompt is None

        def discard_a_tile_not_in_hand(_ai_player, player, _round_state):
            return next(t for t in range(136) if t not in player.tiles)

        monkeypatch.setattr(AIPlayer, "select_discard", discard_a_tile_not_in_hand)
        await router.handle_message(
            conns[0],
            {
                "t": WireClientMessageType.GAME_ACTION,
                "a": WireGameAction.DISCARD,
                "ti": round_state.players[alice_seat].tiles[-1],
            },
        )
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert (conns[0]._close_code, conns[0]._close_reason) == (1011, "internal_error")

    async def test_heartbeat_loop__when_it_raises__should_fail_its_game(self, manager, monkeypatch):
        monkeypatch.setattr(heartbeat_module, "HEARTBEAT_CHECK_INTERVAL", 0)
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        heartbeat_task = manager._heartbeat._tasks["game:game1"]

        async def broken_check(*_args, **_kwargs):
            raise RuntimeError("heartbeat broke")

        monkeypatch.setattr(manager._heartbeat, "_close_stale_connections", broken_check)
        await heartbeat_task
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert [(c._close_code, c._close_reason) for c in conns] == [(1011, "internal_error"), (1011, "internal_error")]

    async def test_fail_game__when_the_game_id_is_reused_before_the_finalizer_runs__should_leave_the_new_game_alone(
        self, seeded_engine, tmp_path
    ):
        collector = ReplayCollector(LocalReplayStorage(tmp_path))
        manager = SessionManager(seeded_engine, replay_collector=collector)
        old_conns = await create_started_game(manager, player_names=["Alice"])
        assert manager.fail_game(manager.get_game("game1"), reason="engine fault") is True

        new_conns = await create_started_game(manager, player_names=["Bob"])
        await wait_for_background_tasks(manager)
        assert old_conns[0]._close_code == 1011
        assert replay_file_path(tmp_path, "game1").exists()
        assert not new_conns[0].is_closed
        assert manager.get_game("game1").ended is False
        assert not manager._heartbeat._tasks["game:game1"].done()
        assert "game1" in collector._buffers

        await manager.shutdown()

    async def test_heartbeat__when_game_cleaned_up__should_stop_game_task(self, manager):
        conns = await create_started_game(
            manager,
            player_names=["P0", "P1", "P2", "P3"],
        )
        assert "game:game1" in manager._heartbeat._tasks
        heartbeat_task = manager._heartbeat._tasks.get("game:game1")

        # leave all players -- game becomes empty, cleanup runs
        for c in conns:
            await manager.leave_game(c)

        assert "game:game1" not in manager._heartbeat._tasks
        assert heartbeat_task.done()


class TestGameEndOwnership:
    async def test_game_end__when_the_game_fails_while_its_end_is_broadcast__should_stay_the_only_finish(
        self, seeded_engine, tmp_path, monkeypatch
    ):
        game_repo = MockGameRepository()
        manager = SessionManager(
            seeded_engine,
            replay_collector=ReplayCollector(LocalReplayStorage(tmp_path)),
            game_repository=game_repo,
        )
        conns = await create_started_game(manager, player_names=["Alice"])
        alice = conns[0]
        alice_seat = manager._players[alice.connection_id].seat
        arrange_final_discard(seeded_engine, game_id="game1", seat=alice_seat)
        game_end_sending = asyncio.Event()
        resume_sending = asyncio.Event()
        send_bytes = alice.send_bytes

        async def pause_on_game_end(data: bytes) -> None:
            if decode(data).get("t") == EVENT_TYPE_INT[EventType.GAME_END]:
                game_end_sending.set()
                await resume_sending.wait()

            await send_bytes(data)

        monkeypatch.setattr(alice, "send_bytes", pause_on_game_end)
        fired = fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await game_end_sending.wait()

        assert manager.fail_game(manager.get_game("game1"), reason="heartbeat failed") is False
        resume_sending.set()
        await fired
        await wait_for_background_tasks(manager)
        assert (alice._close_code, alice._close_reason) == (1000, "game_ended")
        assert SessionErrorCode.INTERNAL_ERROR not in [m.get("code") for m in alice.sent_messages]
        assert game_repo.finish_game.await_count == 1
        assert game_repo.games["game1"]["end_reason"] == GameEndReason.COMPLETED

    async def test_game_end__when_sending_the_end_raises_unexpectedly__should_escalate_to_a_persisted_failure(
        self, seeded_engine, tmp_path, monkeypatch
    ):
        game_repo = MockGameRepository()
        manager = SessionManager(
            seeded_engine,
            replay_collector=ReplayCollector(LocalReplayStorage(tmp_path)),
            game_repository=game_repo,
        )
        conns = await create_started_game(manager, player_names=["Alice"])
        alice = conns[0]
        alice_seat = manager._players[alice.connection_id].seat
        arrange_final_discard(seeded_engine, game_id="game1", seat=alice_seat)
        send_bytes = alice.send_bytes

        async def fail_on_game_end(data: bytes) -> None:
            if decode(data).get("t") == EVENT_TYPE_INT[EventType.GAME_END]:
                raise ValueError("game end payload rejected")

            await send_bytes(data)

        monkeypatch.setattr(alice, "send_bytes", fail_on_game_end)

        await fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await wait_for_background_tasks(manager)
        assert game_repo.games["game1"]["end_reason"] == GameEndReason.ERROR
        assert game_repo.games["game1"]["ended_at"] is not None
        assert replay_file_path(tmp_path, "game1").exists()
        assert [m.get("code") for m in alice.sent_messages][-1] == SessionErrorCode.INTERNAL_ERROR
        assert (alice._close_code, alice._close_reason) == (1011, "internal_error")
        assert manager.get_game("game1") is None
        assert seeded_engine.get_game_state("game1") is None

    async def test_game_end__when_a_close_raises_after_the_finish_is_recorded__should_stay_completed(
        self, seeded_engine, monkeypatch
    ):
        game_repo = MockGameRepository()
        manager = SessionManager(seeded_engine, game_repository=game_repo)
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = manager._players[conns[0].connection_id].seat
        arrange_final_discard(seeded_engine, game_id="game1", seat=alice_seat)
        game = manager.get_game("game1")

        async def close_raises(code: int = 1000, reason: str = "") -> None:
            raise ValueError("close rejected")

        monkeypatch.setattr(conns[0], "close", close_raises)

        await fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await wait_for_background_tasks(manager)
        assert game_repo.games["game1"]["end_reason"] == GameEndReason.COMPLETED
        assert game.end_reason is GameEndReason.COMPLETED
        assert (conns[1]._close_code, conns[1]._close_reason) == (1000, "game_ended")
        assert SessionErrorCode.INTERNAL_ERROR not in [m.get("code") for m in conns[1].sent_messages]


class TestGameEndFromAction:
    async def test_game_end__when_ai_replacement_after_a_kick_ends_game__should_close_remaining_with_1000(
        self, manager
    ):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            return_value=_make_game_end_events(),
        )
        manager._game_service.handle_action = MagicMock(
            side_effect=InvalidGameActionError(action="discard", seat=0, reason="tile not in hand"),
        )

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        assert (conns[0]._close_code, conns[0]._close_reason) == (1008, "invalid_game_action")
        assert (conns[1]._close_code, conns[1]._close_reason) == (1000, "game_ended")

    async def test_game_end__when_action_ends_game__should_close_all_connections(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(return_value=_make_game_end_events())

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        assert conns[0].is_closed
        assert conns[0]._close_code == 1000
        assert conns[0]._close_reason == "game_ended"
        assert conns[1].is_closed

    async def test_game_end__when_ai_replacement_after_invalid_action_ends_game__should_close_remaining_with_1000(
        self, manager
    ):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            return_value=_make_game_end_events(),
        )
        error = InvalidGameActionError(action="discard", seat=0, reason="bad tile")
        manager._game_service.handle_action = MagicMock(side_effect=error)

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
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = manager._players[conns[0].connection_id].seat
        arrange_final_discard(seeded_engine, game_id="game1", seat=alice_seat)

        assert manager.get_playing_game_id("user-0") == "game1"

        fired = fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await fired
        assert manager.get_playing_game_id("user-0") is None
        assert game_repo.games["game1"]["end_reason"] == GameEndReason.COMPLETED
        assert game_repo.games["game1"]["ended_at"] is not None
        assert replay_file_path(tmp_path, "game1").exists()
        assert [(c._close_code, c._close_reason) for c in conns] == [(1000, "game_ended"), (1000, "game_ended")]


class TestGameEndFromLeaveGame:
    async def test_game_end__when_ai_replacement_after_leave_ends_game__should_close_remaining_with_1000(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            return_value=_make_game_end_events(),
        )

        await manager.leave_game(conns[0])
        # Bob's connection should be closed with game_ended
        assert conns[1].is_closed
        assert conns[1]._close_code == 1000
        assert conns[1]._close_reason == "game_ended"
