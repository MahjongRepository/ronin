"""Unit tests for game reconnection in SessionManager."""

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


def _make_snapshot(game_id: str = "game1", seat: int = 0) -> ReconnectionSnapshot:
    """Build a minimal ReconnectionSnapshot for testing."""
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


def _stub_game_state_for_reconnect(manager, current_seat=0, phase=RoundPhase.PLAYING):
    """Override get_game_state to return a mock with round_state for reconnect turn detection."""

    class _MockRoundState:
        phase = RoundPhase.PLAYING
        pending_call_prompt = None
        current_player_seat = current_seat

    _MockRoundState.phase = phase

    class _MockGameState:
        round_state = _MockRoundState()

    manager._game_service.get_game_state = lambda gid: _MockGameState()


class TestSessionManagerReconnect:
    """Tests for SessionManager.reconnect() method."""

    @pytest.mark.asyncio
    async def test_successful_reconnection(self, manager):
        """Player receives game_reconnected message, other players receive player_reconnected."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
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
        await manager.reconnect(new_conn, "game1", alice_token)

        reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert len(reconnect_msgs) == 1
        assert reconnect_msgs[0]["game_id"] == "game1"
        assert reconnect_msgs[0]["seat"] == 0

        bob_msgs = [m for m in bob_conn.sent_messages if m.get("type") == SessionMessageType.PLAYER_RECONNECTED]
        assert len(bob_msgs) == 1
        assert bob_msgs[0]["player_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_reconnect_invalid_token(self, manager):
        """Returns error for unknown session token."""
        await create_started_game(manager, "game1")

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, "game1", "nonexistent-token")

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_NO_SESSION

    @pytest.mark.asyncio
    async def test_reconnect_not_disconnected(self, manager):
        """Returns retryable error when session exists but is not yet disconnected."""
        conns = await create_started_game(manager, "game1", player_names=["Alice"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, "game1", alice_token)

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_RETRY_LATER

    @pytest.mark.asyncio
    async def test_reconnect_game_gone(self, manager):
        """Returns error when game no longer exists."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
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
        await manager.reconnect(new_conn, "game1", alice_token)

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_GAME_GONE

    @pytest.mark.asyncio
    async def test_reconnect_game_mismatch(self, manager):
        """Reconnect on wrong room_id returns reconnect_game_mismatch."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, "wrong_game_id", alice_token)

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_GAME_MISMATCH

    @pytest.mark.asyncio
    async def test_reconnect_retry_later_no_lock(self, manager):
        """Reconnect while lock not yet created returns retryable reconnect_retry_later."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        await manager.leave_game(alice_conn, notify_player=False)

        manager._game_locks.pop("game1", None)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, "game1", alice_token)

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_RETRY_LATER

    @pytest.mark.asyncio
    async def test_reconnect_timer_created_with_preserved_bank(self, manager):
        """Timer is created for reconnected seat with saved bank seconds."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
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
        await manager.reconnect(new_conn, "game1", alice_token)

        reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert len(reconnect_msgs) == 1

        timer = manager._timer_manager.get_timer("game1", 0)
        assert timer is not None
        assert timer.bank_seconds == 1.5

        reconnected_session = manager._session_store.get_session(alice_token)
        assert reconnected_session is not None
        assert reconnected_session.remaining_bank_seconds is None


class TestBankTimePreservation:
    """Tests for bank time preservation across disconnect/reconnect."""

    @pytest.mark.asyncio
    async def test_disconnect_mid_turn_deducts_elapsed_time(self, manager):
        """Disconnect mid-turn deducts elapsed time from saved bank."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        timer = manager._timer_manager.get_timer("game1", 0)
        assert timer is not None

        initial_bank = timer.bank_seconds
        # simulate 1 second of elapsed turn time
        timer._turn_start_time = time.monotonic() - 1.0

        await manager.leave_game(alice_conn, notify_player=False)

        session = manager._session_store.get_session(alice_token)
        assert session is not None
        assert session.remaining_bank_seconds is not None
        assert session.remaining_bank_seconds < initial_bank
        assert session.remaining_bank_seconds == pytest.approx(initial_bank - 1.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_disconnect_during_meld_prompt_preserves_bank_unchanged(self, manager):
        """Disconnect during meld prompt preserves bank time unchanged (meld timers don't consume bank)."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
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
    """Tests for turn state being sent on reconnection."""

    @pytest.mark.asyncio
    async def test_pending_turn_actions_sent_on_reconnection(self, manager):
        """If it's the reconnected player's turn, draw events are resent."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
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
        await manager.reconnect(new_conn, "game1", alice_token)

        draw_msgs = [m for m in new_conn.sent_messages if m.get("type") == EventType.DRAW]
        assert len(draw_msgs) == 1
        assert draw_msgs[0]["tile_id"] == 42


class TestReconnectEdgeCases:
    """Tests for reconnect edge cases."""

    @pytest.mark.asyncio
    async def test_reconnect_in_room_rejected(self, manager):
        """Reconnect while in a room returns error."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token
        await manager.leave_game(alice_conn, notify_player=False)

        manager.create_room("room2")
        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.join_room(new_conn, "room2", "Alice2")

        await manager.reconnect(new_conn, "game1", alice_token)

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        reconnect_errors = [m for m in error_msgs if m["code"] == SessionErrorCode.RECONNECT_IN_ROOM]
        assert len(reconnect_errors) == 1

    @pytest.mark.asyncio
    async def test_reconnect_already_active_rejected(self, manager):
        """Reconnect while already in a game returns error."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token
        await manager.leave_game(alice_conn, notify_player=False)

        bob_conn = conns[1]
        await manager.reconnect(bob_conn, "game1", alice_token)

        error_msgs = [m for m in bob_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        reconnect_errors = [m for m in error_msgs if m["code"] == SessionErrorCode.RECONNECT_ALREADY_ACTIVE]
        assert len(reconnect_errors) == 1

    @pytest.mark.asyncio
    async def test_reconnect_snapshot_failure_restores_ai(self, manager):
        """If snapshot building fails, the AI player is re-added at the seat."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
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
        await manager.reconnect(new_conn, "game1", alice_token)

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert any(m["code"] == SessionErrorCode.RECONNECT_SNAPSHOT_FAILED for m in error_msgs)

        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", "Alice")

    @pytest.mark.asyncio
    async def test_reconnect_snapshot_exception_restores_ai(self, manager):
        """If snapshot building raises, the AI player is re-added at the seat."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        def exploding_snapshot(gid, seat):
            raise RuntimeError("snapshot boom")

        manager._game_service.build_reconnection_snapshot = exploding_snapshot

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
        with pytest.raises(RuntimeError, match="snapshot boom"):
            await manager.reconnect(new_conn, "game1", alice_token)

        # AI player was restored at the seat
        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", "Alice")

    @pytest.mark.asyncio
    async def test_reconnect_no_seat_rejected(self, manager):
        """Reconnect with session that has no seat returns error."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        await manager.leave_game(alice_conn, notify_player=False)

        session = manager._session_store.get_session(alice_token)
        session.seat = None

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, "game1", alice_token)

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert any(m["code"] == SessionErrorCode.RECONNECT_NO_SEAT for m in error_msgs)

    @pytest.mark.asyncio
    async def test_reconnect_cleans_stale_connections(self, manager):
        """Stale connections at the seat are removed before adding the new player."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
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
        await manager.reconnect(new_conn, "game1", alice_token)

        assert alice_conn.connection_id not in game.players
        assert new_conn.connection_id in game.players

        assert alice_conn.is_closed

    @pytest.mark.asyncio
    async def test_reconnect_rejected_when_session_cleared_before_lock(self, manager):
        """Reconnect is rejected if session is no longer disconnected when the lock is acquired.

        Simulates a concurrent reconnect completing (clearing disconnected_at)
        between prevalidation and the lock-internal revalidation.
        """
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
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

        async def patched_validate(connection, room_id, token):
            result = await original_validate(connection, room_id, token)
            if result is not None:
                # Simulate concurrent reconnect completing before lock acquisition
                session.disconnected_at = None
            return result

        manager._validate_reconnect = patched_validate

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, "game1", alice_token)

        manager._validate_reconnect = original_validate

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert any(m["code"] == SessionErrorCode.RECONNECT_NO_SESSION for m in error_msgs)

    @pytest.mark.asyncio
    async def test_reconnect_no_draw_event_when_game_state_none(self, manager):
        """No draw event sent if get_game_state returns None after reconnect."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        manager._game_service.get_game_state = lambda gid: None

        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, "game1", alice_token)

        # reconnect succeeds, but no draw event sent
        reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert len(reconnect_msgs) == 1
        draw_msgs = [m for m in new_conn.sent_messages if m.get("type") == EventType.DRAW]
        assert len(draw_msgs) == 0

    @pytest.mark.asyncio
    async def test_reconnect_no_draw_event_in_non_playing_phase(self, manager):
        """No draw event sent when round is not in PLAYING phase."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        _stub_game_state_for_reconnect(manager, current_seat=0, phase=RoundPhase.FINISHED)
        manager._game_service.is_round_advance_pending = lambda gid: False

        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, "game1", alice_token)

        draw_msgs = [m for m in new_conn.sent_messages if m.get("type") == EventType.DRAW]
        assert len(draw_msgs) == 0

    @pytest.mark.asyncio
    async def test_reconnect_no_draw_event_when_call_prompt_pending(self, manager):
        """No draw event sent when a call prompt is pending."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_player = manager._players[alice_conn.connection_id]
        alice_token = alice_player.session_token

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        # stub game state with a pending call prompt
        class _MockRoundState:
            phase = RoundPhase.PLAYING
            pending_call_prompt = object()  # truthy value = prompt exists
            current_player_seat = 0

        class _MockGameState:
            round_state = _MockRoundState()

        manager._game_service.get_game_state = lambda gid: _MockGameState()
        manager._game_service.is_round_advance_pending = lambda gid: False

        await manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.reconnect(new_conn, "game1", alice_token)

        draw_msgs = [m for m in new_conn.sent_messages if m.get("type") == EventType.DRAW]
        assert len(draw_msgs) == 0


class TestReconnectThenPlay:
    """Tests for performing game actions after reconnecting."""

    @pytest.mark.asyncio
    async def test_reconnect_then_play(self, manager):
        """Player reconnects and can perform game actions normally."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        _stub_game_state_for_reconnect(manager)

        new_conn, _new_token = await disconnect_and_reconnect(manager, alice_conn, "game1")
        new_conn._outbox.clear()

        await manager.handle_game_action(new_conn, GameAction.DISCARD, {"tile_id": 1})

        action_msgs = [m for m in new_conn.sent_messages if m.get("type") == EventType.DRAW]
        assert len(action_msgs) == 1
        assert action_msgs[0]["player"] == "Alice"
        assert action_msgs[0]["action"] == GameAction.DISCARD


class TestMultipleReconnects:
    """Tests for multiple disconnect/reconnect cycles."""

    @pytest.mark.asyncio
    async def test_multiple_reconnects_bank_decreases(self, manager):
        """Bank time monotonically decreases across multiple disconnect/reconnect cycles."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])
        alice_conn = conns[0]

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot
        _stub_game_state_for_reconnect(manager)

        bank_values = []
        current_conn = alice_conn

        for _ in range(3):
            # simulate 0.5s of elapsed turn time before each disconnect
            timer = manager._timer_manager.get_timer("game1", 0)
            assert timer is not None
            timer._turn_start_time = time.monotonic() - 0.5

            player = manager._players[current_conn.connection_id]
            token = player.session_token

            await manager.leave_game(current_conn, notify_player=False)

            new_conn = MockConnection()
            manager.register_connection(new_conn)
            await manager.reconnect(new_conn, "game1", token)

            timer = manager._timer_manager.get_timer("game1", 0)
            assert timer is not None
            bank_values.append(timer.bank_seconds)

            current_conn = new_conn

        # bank should be strictly decreasing
        for i in range(1, len(bank_values)):
            assert bank_values[i] < bank_values[i - 1], f"Bank did not decrease: {bank_values}"


class TestAllHumansDisconnected:
    """Tests for game cancellation when all humans disconnect."""

    @pytest.mark.asyncio
    async def test_all_humans_disconnected_game_canceled_no_replay_persisted(self, manager):
        """When all humans disconnect, the game is canceled and replay is discarded."""
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
            "game1",
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
