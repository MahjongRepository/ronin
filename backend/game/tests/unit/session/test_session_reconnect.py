import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from game.logic.enums import GameAction, PlayerAction, TimeoutType, WaitKind, WindName
from game.logic.events import (
    DrawEvent,
    EventType,
    SeatTarget,
    ServiceEvent,
)
from game.logic.service import Awaiting
from game.logic.types import (
    AvailableActionItem,
    GamePlayerInfo,
    PlayerReconnectState,
    ReconnectionSnapshot,
)
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.messaging.wire_enums import WireClientMessageType
from game.server.router import MessageRouter
from game.session.manager import SessionManager
from game.session.models import SessionData
from game.session.replay_collector import ReplayCollector
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.mocks import FakeGameRepository, MockConnection, MockGameService
from game.tests.unit.session.helpers import (
    arrange_final_discard,
    create_started_game,
    current_wait_id,
    disconnect_and_reconnect,
    run_timeout,
    wait_for_background_tasks,
)
from game.wire.compact import encode_draw
from game.wire.events import EVENT_TYPE_INT


def _make_snapshot(game_id: str = "game1", seat: int = 0) -> ReconnectionSnapshot:
    return ReconnectionSnapshot(
        game_id=game_id,
        players=[
            GamePlayerInfo(seat=0, name="Alice", is_ai_player=False),
            GamePlayerInfo(seat=1, name="AI", is_ai_player=True),
            GamePlayerInfo(seat=2, name="AI", is_ai_player=True),
            GamePlayerInfo(seat=3, name="AI", is_ai_player=True),
        ],
        dealer_seat=0,
        dealer_dice=((1, 2), (3, 4)),
        seat=seat,
        round_wind=WindName.EAST,
        round_number=1,
        current_player_seat=0,
        dora_indicators=[0],
        honba_sticks=0,
        riichi_sticks=0,
        my_tiles=[1, 2, 3],
        dice=(3, 4),
        tiles_remaining=70,
        player_states=[
            PlayerReconnectState(seat=i, score=25000, discards=[], melds=[], is_riichi=False) for i in range(4)
        ],
        is_furiten=False,
    )


def _awaiting(kind: WaitKind, *, seat: int) -> Awaiting:
    return Awaiting(kind=kind, seats=frozenset({seat}), wait_id=1, round_number=0)


def _make_draw_event(*, seat: int, tile_id: int) -> ServiceEvent:
    return ServiceEvent(
        data=DrawEvent(
            seat=seat,
            tile_id=tile_id,
            available_actions=[AvailableActionItem(action=PlayerAction.DISCARD)],
            target=SeatTarget(seat=seat),
        ),
    )


class TestSessionManagerReconnect:
    @pytest.mark.asyncio
    async def test_reconnect__when_session_disconnected__should_send_game_reconnected_and_notify_others(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn, bob_conn = conns
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0).model_copy(update={"is_furiten": True})
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        await manager.leave_game(alice_conn, notify_player=False)
        bob_conn._outbox.clear()

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert len(reconnect_msgs) == 1
        assert reconnect_msgs[0]["gid"] == "game1"
        assert reconnect_msgs[0]["s"] == 0
        assert reconnect_msgs[0]["f"] is True
        bob_msgs = [m for m in bob_conn.sent_messages if m.get("type") == SessionMessageType.PLAYER_RECONNECTED]
        assert len(bob_msgs) == 1
        assert bob_msgs[0]["player_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_reconnect__when_token_unknown__should_return_no_session_error(self, manager):
        await create_started_game(manager)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token="nonexistent-token")
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_NO_SESSION

    @pytest.mark.asyncio
    async def test_reconnect__when_session_still_connected__should_return_retry_later_error(self, manager):
        conns = await create_started_game(manager, player_names=["Alice"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_RETRY_LATER

    @pytest.mark.asyncio
    async def test_reconnect__when_game_cleaned_up__should_return_game_gone_error(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        # disconnect both players so the game is cleaned up
        await manager.leave_game(alice_conn, notify_player=False)
        await manager.leave_game(conns[1], notify_player=False)
        assert manager._games.get("game1") is None

        # manually re-create the session to test the game_gone path
        # (cleanup_game removes all sessions, so put it back with disconnected state)
        session = SessionData(
            session_token=alice_token,
            player_name="Alice",
            game_id="game1",
            seat=0,
            disconnected_at=time.monotonic(),
        )
        manager._session_store._sessions[alice_token] = session

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_GAME_GONE

    @pytest.mark.asyncio
    async def test_reconnect__when_game_id_differs_from_session__should_return_game_mismatch_error(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token
        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="wrong_game_id", session_token=alice_token)
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_GAME_MISMATCH

    @pytest.mark.asyncio
    async def test_reconnect__when_game_lock_missing__should_return_retry_later_error(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        await manager.leave_game(alice_conn, notify_player=False)
        manager._game_locks.pop("game1", None)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_RETRY_LATER

    @pytest.mark.asyncio
    async def test_reconnect__when_bank_saved_on_leave__should_restore_timer_with_that_bank(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        await manager.leave_game(alice_conn, notify_player=False)
        # override the bank time that leave_game saved
        session = manager._session_store.get_session(alice_token)
        session.remaining_bank_seconds = 1.5

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert len(reconnect_msgs) == 1
        timer = manager._timer_manager.get_timer("game1", 0)
        assert timer is not None
        assert timer.bank_seconds == 1.5
        reconnected_session = manager._session_store.get_session(alice_token)
        assert reconnected_session is not None
        assert reconnected_session.remaining_bank_seconds is None


class TestBankTimePreservation:
    @pytest.mark.asyncio
    async def test_bank_time__when_player_leaves_mid_turn__should_save_bank_minus_elapsed_overtime(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token
        timer = manager._timer_manager.get_timer("game1", 0)
        assert timer is not None

        initial_bank = timer.bank_seconds
        base_time = timer._config.base_turn_seconds
        # simulate elapsed time that exceeds base time by 1 second
        timer._turn_start_time = time.monotonic() - (base_time + 1.0)

        await manager.leave_game(alice_conn, notify_player=False)
        session = manager._session_store.get_session(alice_token)
        assert session is not None
        assert session.remaining_bank_seconds is not None
        assert session.remaining_bank_seconds < initial_bank
        assert session.remaining_bank_seconds == pytest.approx(initial_bank - 1.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_bank_time__when_player_leaves_during_meld_prompt__should_save_bank_unchanged(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token
        timer = manager._timer_manager.get_timer("game1", 0)
        assert timer is not None
        initial_bank = timer.bank_seconds

        # start a meld timer (fixed timer, _turn_start_time = None)
        timer.start_meld_timer(AsyncMock())
        assert timer._turn_start_time is None

        await manager.leave_game(alice_conn, notify_player=False)
        session = manager._session_store.get_session(alice_token)
        assert session is not None
        assert session.remaining_bank_seconds is not None
        assert session.remaining_bank_seconds == initial_bank


class TestReconnectTurnState:
    async def test_reconnect__when_it_is_players_turn__should_resend_draw_event(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_token = manager._players[conns[0].connection_id].session_token
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: _make_snapshot("game1", seat=0)
        manager._game_service.build_draw_event_for_seat = lambda gid, seat: [_make_draw_event(seat=0, tile_id=42)]
        manager._game_service.get_awaiting = lambda gid: _awaiting(WaitKind.TURN, seat=0)
        await manager.leave_game(conns[0], notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        reconnected = next(m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED)
        draw_msgs = [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert reconnected["wi"] == 1
        assert [(m["d"], m["wi"]) for m in draw_msgs] == [(encode_draw(0, 42), 1)]
        assert manager._timer_manager.get_timer("game1", 0).task is not None

        await manager.shutdown()

    @pytest.mark.parametrize(
        "awaiting",
        [
            _awaiting(WaitKind.TURN, seat=1),
            _awaiting(WaitKind.CALL, seat=0),
            _awaiting(WaitKind.ROUND_ADVANCE, seat=0),
        ],
    )
    async def test_reconnect__when_the_game_awaits_no_turn_of_the_seat__should_send_no_draw_event(
        self, manager, awaiting
    ):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_token = manager._players[conns[0].connection_id].session_token
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: _make_snapshot("game1", seat=0)
        manager._game_service.build_draw_event_for_seat = lambda gid, seat: [_make_draw_event(seat=0, tile_id=42)]
        manager._game_service.get_awaiting = lambda gid: awaiting
        await manager.leave_game(conns[0], notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        assert [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]] == []
        assert manager._timer_manager.get_timer("game1", 0).task is None


class TestReconnectEdgeCases:
    @pytest.mark.asyncio
    async def test_reconnect__when_session_token_still_active__should_return_already_active_error(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token
        await manager.leave_game(alice_conn, notify_player=False)

        bob_conn = conns[1]
        await manager.reconnect(bob_conn, game_id="game1", session_token=alice_token)
        error_msgs = [m for m in bob_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        reconnect_errors = [m for m in error_msgs if m["code"] == SessionErrorCode.RECONNECT_ALREADY_ACTIVE]
        assert len(reconnect_errors) == 1

    @pytest.mark.asyncio
    async def test_reconnect__when_snapshot_unavailable__should_return_snapshot_failed_and_restore_ai(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: None

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, seat):
            replace_calls.append((game_id, seat))
            return original_replace(game_id, seat)

        manager._game_service.replace_with_ai_player = tracking_replace
        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        replace_calls.clear()
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert any(m["code"] == SessionErrorCode.RECONNECT_SNAPSHOT_FAILED for m in error_msgs)
        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", 0)

    @pytest.mark.asyncio
    async def test_reconnect__when_session_has_no_seat__should_return_no_seat_error(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token
        await manager.leave_game(alice_conn, notify_player=False)

        session = manager._session_store.get_session(alice_token)
        session.seat = None

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert any(m["code"] == SessionErrorCode.RECONNECT_NO_SEAT for m in error_msgs)

    @pytest.mark.asyncio
    async def test_reconnect__when_old_connection_still_in_game__should_evict_and_close_it(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        # manually mark session as disconnected without removing from game.players
        session = manager._session_store.get_session(alice_token)
        session.disconnected_at = time.monotonic()
        game = manager._games["game1"]
        assert alice_conn.connection_id in game.players

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        assert alice_conn.connection_id not in game.players
        assert new_conn.connection_id in game.players
        assert alice_conn.is_closed

    @pytest.mark.asyncio
    async def test_reconnect__when_session_reconnected_concurrently_before_lock__should_return_no_session_error(
        self, manager
    ):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        await manager.leave_game(alice_conn, notify_player=False)

        session = manager._session_store.get_session(alice_token)
        # Bypass prevalidation by directly calling reconnect internals:
        # patch _validate_reconnect to return the expected tuple while the
        # session is still marked disconnected, then clear disconnected_at
        # to simulate a concurrent reconnect having completed.
        original_validate = manager._validate_reconnect

        def patched_validate(connection, game_id, session_token):
            result = original_validate(connection, game_id=game_id, session_token=session_token)
            if result is not None:
                # Simulate concurrent reconnect completing before lock acquisition
                session.disconnected_at = None

            return result

        manager._validate_reconnect = patched_validate
        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert any(m["code"] == SessionErrorCode.RECONNECT_NO_SESSION for m in error_msgs)

        manager._validate_reconnect = original_validate

    @pytest.mark.asyncio
    async def test_reconnect__when_connection_removed_before_lock__should_return_silently_without_registering(
        self, manager
    ):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        await manager.leave_game(alice_conn, notify_player=False)

        # Patch _validate_reconnect to simulate auth timeout removing the
        # connection from _connections between prevalidation and lock acquisition.
        original_validate = manager._validate_reconnect

        def patched_validate(connection, game_id, session_token):
            result = original_validate(connection, game_id=game_id, session_token=session_token)
            if result is not None:
                manager._connections.pop(connection.connection_id, None)

            return result

        manager._validate_reconnect = patched_validate
        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        # Should silently return without registering or sending errors
        reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert len(reconnect_msgs) == 0
        assert new_conn.connection_id not in manager._players

        manager._validate_reconnect = original_validate

    @pytest.mark.asyncio
    async def test_reconnect__when_snapshot_raises__should_fail_the_game(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        alice_token = manager._players[conns[0].connection_id].session_token
        await manager.leave_game(conns[0], notify_player=False)

        def raise_error(gid, seat):
            raise RuntimeError("snapshot failed")

        manager._game_service.build_reconnection_snapshot = raise_error
        new_conn = MockConnection(game_id="game1")
        router.handle_connect(new_conn)

        await router.handle_message(new_conn, {"t": WireClientMessageType.RECONNECT, "game_ticket": alice_token})
        await router.handle_disconnect(new_conn)
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert (new_conn._close_code, new_conn._close_reason) == (1011, "internal_error")
        assert (conns[1]._close_code, conns[1]._close_reason) == (1011, "internal_error")


class TestReconnectToEndedGame:
    async def test_reconnect__when_game_ended_while_player_was_away__should_refuse_with_game_gone(self, seeded_engine):
        manager = SessionManager(seeded_engine, game_repository=FakeGameRepository())
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = manager._players[conns[0].connection_id].seat
        bob_token = manager._players[conns[1].connection_id].session_token
        await manager.leave_game(conns[1], notify_player=False)
        arrange_final_discard(seeded_engine, game_id="game1", seat=alice_seat)
        await run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=alice_seat)
        assert manager.get_game("game1").ended is True

        reconnecting = MockConnection()
        manager.register_connection(reconnecting)
        await manager.reconnect(reconnecting, game_id="game1", session_token=bob_token)
        assert [m["code"] for m in reconnecting.sent_messages] == [SessionErrorCode.RECONNECT_GAME_GONE]
        assert manager._session_store.get_session(bob_token).disconnected_at is not None


class TestReconnectThenPlay:
    @pytest.mark.asyncio
    async def test_reconnect__when_discard_sent_after_reconnect__should_handle_it_as_reconnected_player(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        new_conn, _new_token = await disconnect_and_reconnect(manager, alice_conn, game_id="game1")
        new_conn._outbox.clear()

        await manager.handle_game_action(
            new_conn, action=GameAction.DISCARD, data={"tile_id": 1}, wait_id=current_wait_id(manager)
        )
        action_msgs = [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(action_msgs) == 1
        assert action_msgs[0]["seat"] == 0
        assert action_msgs[0]["action"] == GameAction.DISCARD


class TestMultipleReconnects:
    @pytest.mark.asyncio
    async def test_reconnect__when_repeated_after_overtime__should_decrease_bank_each_time(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        bank_values = []
        current_conn = alice_conn

        for _ in range(3):
            # simulate elapsed time that exceeds base time by 0.5s
            timer = manager._timer_manager.get_timer("game1", 0)
            assert timer is not None

            base_time = timer._config.base_turn_seconds
            timer._turn_start_time = time.monotonic() - (base_time + 0.5)

            player = manager._players[current_conn.connection_id]
            token = player.session_token
            await manager.leave_game(current_conn, notify_player=False)

            new_conn = MockConnection()
            manager.register_connection(new_conn)
            await manager.reconnect(new_conn, game_id="game1", session_token=token)
            timer = manager._timer_manager.get_timer("game1", 0)
            assert timer is not None
            bank_values.append(timer.bank_seconds)

            current_conn = new_conn

        # bank should be strictly decreasing
        for i in range(1, len(bank_values)):
            assert bank_values[i] < bank_values[i - 1], f"Bank did not decrease: {bank_values}"


class TestAllHumansDisconnected:
    @pytest.mark.asyncio
    async def test_reconnect__when_all_humans_leave__should_discard_replay_without_saving(self, manager):
        # Create manager with a replay collector to verify it's not persisted
        mock_replay = MagicMock(spec=ReplayCollector)
        mock_replay.start_game = MagicMock()
        mock_replay.collect_events = MagicMock()
        mock_replay.save = AsyncMock()
        mock_replay.cleanup_game = MagicMock()

        game_service = MockGameService()
        manager_with_replay = SessionManager(
            game_service, replay_collector=mock_replay, game_repository=FakeGameRepository()
        )

        conns = await create_started_game(
            manager_with_replay,
            player_names=["Alice", "Bob"],
        )
        mock_replay.reset_mock()

        # disconnect both human players
        await manager_with_replay.leave_game(conns[0], notify_player=False)
        await manager_with_replay.leave_game(conns[1], notify_player=False)
        # game should be cleaned up
        assert manager_with_replay.get_game("game1") is None
        # replay should be cleaned up (discarded), not saved
        mock_replay.save.assert_not_awaited()
        mock_replay.cleanup_game.assert_called_once_with("game1")
