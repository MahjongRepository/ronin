import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from game.logic.enums import GameAction, PlayerAction, RoundPhase, WindName
from game.logic.events import (
    DrawEvent,
    EventType,
    SeatTarget,
    ServiceEvent,
)
from game.logic.types import (
    AvailableActionItem,
    GamePlayerInfo,
    PlayerReconnectState,
    ReconnectionSnapshot,
)
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.session.manager import SessionManager
from game.session.models import SessionData
from game.session.replay_collector import ReplayCollector
from game.tests.mocks import MockConnection, MockGameService
from game.tests.unit.session.helpers import create_started_game, disconnect_and_reconnect
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
    )


def _stub_game_state_for_reconnect(manager, current_seat=0, phase=RoundPhase.PLAYING, pending_call_prompt=None):

    class _MockRoundState:
        pass

    round_state = _MockRoundState()
    round_state.phase = phase
    round_state.pending_call_prompt = pending_call_prompt
    round_state.current_player_seat = current_seat

    class _MockGameState:
        pass

    _MockGameState.round_state = round_state

    manager._game_service.get_game_state = lambda gid: _MockGameState()


class TestSessionManagerReconnect:
    @pytest.mark.asyncio
    async def test_reconnect__when_session_disconnected__should_send_game_reconnected_and_notify_others(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn, bob_conn = conns

        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        await manager.leave_game(alice_conn, notify_player=False)
        bob_conn._outbox.clear()

        _stub_game_state_for_reconnect(manager)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)

        reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert len(reconnect_msgs) == 1
        assert reconnect_msgs[0]["gid"] == "game1"
        assert reconnect_msgs[0]["s"] == 0

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
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
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
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
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
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
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
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        await manager.leave_game(alice_conn, notify_player=False)

        # override the bank time that leave_game saved
        session = manager._session_store.get_session(alice_token)
        session.remaining_bank_seconds = 1.5

        _stub_game_state_for_reconnect(manager)

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
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
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
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
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
    @pytest.mark.asyncio
    async def test_reconnect__when_it_is_players_turn__should_resend_draw_event(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        draw_event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                seat=0,
                tile_id=42,
                available_actions=[AvailableActionItem(action=PlayerAction.DISCARD)],
                target="seat_0",
            ),
            target=SeatTarget(seat=0),
        )
        manager._game_service.build_draw_event_for_seat = lambda gid, seat: [draw_event]

        _stub_game_state_for_reconnect(manager, current_seat=0)
        manager._game_service.is_round_advance_pending = lambda gid: False

        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)

        draw_msgs = [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(draw_msgs) == 1
        assert draw_msgs[0]["d"] == encode_draw(0, 42)


class TestReconnectEdgeCases:
    @pytest.mark.asyncio
    async def test_reconnect__when_session_token_still_active__should_return_already_active_error(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
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
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        manager._game_service.build_reconnection_snapshot = lambda gid, seat: None

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_with_ai_player = tracking_replace

        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        replace_calls.clear()
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert any(m["code"] == SessionErrorCode.RECONNECT_SNAPSHOT_FAILED for m in error_msgs)

        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", "Alice")

    @pytest.mark.asyncio
    async def test_reconnect__when_session_has_no_seat__should_return_no_seat_error(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
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
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
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

        _stub_game_state_for_reconnect(manager)

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
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        await manager.leave_game(alice_conn, notify_player=False)
        _stub_game_state_for_reconnect(manager)

        session = manager._session_store.get_session(alice_token)

        # Bypass prevalidation by directly calling reconnect internals:
        # patch _validate_reconnect to return the expected tuple while the
        # session is still marked disconnected, then clear disconnected_at
        # to simulate a concurrent reconnect having completed.
        original_validate = manager._validate_reconnect

        async def patched_validate(connection, game_id, session_token):
            result = await original_validate(connection, game_id=game_id, session_token=session_token)
            if result is not None:
                # Simulate concurrent reconnect completing before lock acquisition
                session.disconnected_at = None
            return result

        manager._validate_reconnect = patched_validate

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)

        manager._validate_reconnect = original_validate

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert any(m["code"] == SessionErrorCode.RECONNECT_NO_SESSION for m in error_msgs)

    @pytest.mark.asyncio
    async def test_reconnect__when_connection_removed_before_lock__should_return_silently_without_registering(
        self, manager
    ):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        await manager.leave_game(alice_conn, notify_player=False)
        _stub_game_state_for_reconnect(manager)

        # Patch _validate_reconnect to simulate auth timeout removing the
        # connection from _connections between prevalidation and lock acquisition.
        original_validate = manager._validate_reconnect

        async def patched_validate(connection, game_id, session_token):
            result = await original_validate(connection, game_id=game_id, session_token=session_token)
            if result is not None:
                manager._connections.pop(connection.connection_id, None)
            return result

        manager._validate_reconnect = patched_validate

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)

        manager._validate_reconnect = original_validate

        # Should silently return without registering or sending errors
        reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert len(reconnect_msgs) == 0
        assert new_conn.connection_id not in manager._players

    @pytest.mark.asyncio
    async def test_reconnect__when_game_state_missing__should_send_no_draw_event(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        manager._game_service.get_game_state = lambda gid: None

        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)

        # reconnect succeeds, but no draw event sent
        reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert len(reconnect_msgs) == 1
        draw_msgs = [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(draw_msgs) == 0

    @pytest.mark.asyncio
    async def test_reconnect__when_snapshot_raises__should_restore_ai_and_propagate(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        def raise_error(gid, seat):
            raise RuntimeError("snapshot failed")

        manager._game_service.build_reconnection_snapshot = raise_error

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_with_ai_player = tracking_replace

        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        replace_calls.clear()

        with pytest.raises(RuntimeError, match="snapshot failed"):
            await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)

        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", "Alice")

    @pytest.mark.asyncio
    async def test_reconnect__when_call_prompt_pending__should_send_no_draw_event(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        _stub_game_state_for_reconnect(manager, current_seat=0, pending_call_prompt=object())
        manager._game_service.is_round_advance_pending = lambda gid: False

        # Mock build_draw_event_for_seat to return a draw event so the assertion
        # would fail if the pending_call_prompt check were missing.
        draw_event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                seat=0,
                tile_id=42,
                available_actions=[AvailableActionItem(action=PlayerAction.DISCARD)],
                target="seat_0",
            ),
            target=SeatTarget(seat=0),
        )
        manager._game_service.build_draw_event_for_seat = lambda gid, seat: [draw_event]

        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)

        draw_msgs = [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(draw_msgs) == 0

    @pytest.mark.asyncio
    async def test_reconnect__when_round_not_playing__should_send_no_draw_event(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        _stub_game_state_for_reconnect(manager, current_seat=0, phase=RoundPhase.FINISHED)
        manager._game_service.is_round_advance_pending = lambda gid: False

        # Mock build_draw_event_for_seat to return a draw event so the assertion
        # would fail if the phase check were missing.
        draw_event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                seat=0,
                tile_id=42,
                available_actions=[AvailableActionItem(action=PlayerAction.DISCARD)],
                target="seat_0",
            ),
            target=SeatTarget(seat=0),
        )
        manager._game_service.build_draw_event_for_seat = lambda gid, seat: [draw_event]

        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, game_id="game1", session_token=alice_token)

        draw_msgs = [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(draw_msgs) == 0


class TestReconnectThenPlay:
    @pytest.mark.asyncio
    async def test_reconnect__when_discard_sent_after_reconnect__should_handle_it_as_reconnected_player(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        _stub_game_state_for_reconnect(manager)

        new_conn, _new_token = await disconnect_and_reconnect(manager, alice_conn, game_id="game1")
        new_conn._outbox.clear()

        await manager.handle_game_action(new_conn, action=GameAction.DISCARD, data={"tile_id": 1})

        action_msgs = [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(action_msgs) == 1
        assert action_msgs[0]["player"] == "Alice"
        assert action_msgs[0]["action"] == GameAction.DISCARD


class TestMultipleReconnects:
    @pytest.mark.asyncio
    async def test_reconnect__when_repeated_after_overtime__should_decrease_bank_each_time(self, manager):
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        _stub_game_state_for_reconnect(manager)

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
        mock_replay.save_and_cleanup = AsyncMock()
        mock_replay.cleanup_game = MagicMock()

        game_service = MockGameService()
        manager_with_replay = SessionManager(game_service, replay_collector=mock_replay)

        conns = await create_started_game(
            manager_with_replay,
            num_ai_players=2,
            player_names=["Alice", "Bob"],
        )
        mock_replay.reset_mock()

        # disconnect both human players
        await manager_with_replay.leave_game(conns[0], notify_player=False)
        await manager_with_replay.leave_game(conns[1], notify_player=False)

        # game should be cleaned up
        assert manager_with_replay.get_game("game1") is None

        # replay should be cleaned up (discarded), not saved
        mock_replay.save_and_cleanup.assert_not_awaited()
        mock_replay.cleanup_game.assert_called_once_with("game1")
