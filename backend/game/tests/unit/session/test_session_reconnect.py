import time
from unittest.mock import MagicMock

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
from game.session.models import PlayerSpec
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import MockConnection
from game.tests.unit.session.helpers import (
    arrange_final_discard,
    create_started_game,
    current_wait_id,
    disconnect_and_reconnect,
    game_of,
    participant_of,
    run_timeout,
    runtime_of,
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
        round_history=[],
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
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn, bob_conn = conns
        alice_token = participant_of(manager, alice_conn).ticket

        snapshot = _make_snapshot("game1", seat=0).model_copy(update={"is_furiten": True})
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        manager.leave_game(alice_conn, notify_player=False)
        bob_conn._outbox.clear()

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
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
        create_started_game(manager)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, game_id="game1", session_token="nonexistent-token")
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_NO_SESSION

    @pytest.mark.asyncio
    async def test_reconnect__when_session_still_connected__should_return_retry_later_error(self, manager):
        conns = create_started_game(manager, player_names=["Alice"])
        alice_conn = conns[0]
        alice_token = participant_of(manager, alice_conn).ticket

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_RETRY_LATER

    @pytest.mark.asyncio
    async def test_reconnect__when_game_id_differs_from_session__should_return_game_mismatch_error(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_token = participant_of(manager, alice_conn).ticket
        manager.leave_game(alice_conn, notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, game_id="wrong_game_id", session_token=alice_token)
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_GAME_MISMATCH


class TestBankTimePreservation:
    @pytest.mark.asyncio
    async def test_bank_time__when_player_leaves_mid_turn__should_keep_bank_minus_overtime_for_the_reconnect(
        self, manager
    ):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice = participant_of(manager, alice_conn)
        timer = alice.timer
        initial_bank = timer._bank_seconds
        timer._turn_start_time = time.monotonic() - (timer._config.base_turn_seconds + 1.0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: _make_snapshot("game1", seat=0)

        manager.leave_game(alice_conn, notify_player=False)
        bank_after_leave = timer._bank_seconds
        assert bank_after_leave == pytest.approx(initial_bank - 1.0, abs=0.1)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, game_id="game1", session_token=alice.ticket)
        assert alice.connection is new_conn
        assert alice.timer._bank_seconds == bank_after_leave

    @pytest.mark.asyncio
    async def test_bank_time__when_player_leaves_during_meld_prompt__should_keep_bank_unchanged(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        timer = participant_of(manager, alice_conn).timer
        initial_bank = timer._bank_seconds
        timer.start_meld_timer(MagicMock())

        manager.leave_game(alice_conn, notify_player=False)
        assert timer._bank_seconds == initial_bank


class TestReconnectTurnState:
    async def test_reconnect__when_it_is_players_turn__should_resend_draw_event(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_token = participant_of(manager, conns[0]).ticket
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: _make_snapshot("game1", seat=0)
        manager._game_service.build_draw_event_for_seat = lambda gid, seat: [_make_draw_event(seat=0, tile_id=42)]
        manager._game_service.get_awaiting = lambda gid: _awaiting(WaitKind.TURN, seat=0)
        manager.leave_game(conns[0], notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        reconnected = next(m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED)
        draw_msgs = [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert reconnected["wi"] == 1
        assert [(m["d"], m["wi"]) for m in draw_msgs] == [(encode_draw(0, 42), 1)]
        assert game_of(manager).at_seat(0).timer.task is not None

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
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_token = participant_of(manager, conns[0]).ticket
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: _make_snapshot("game1", seat=0)
        manager._game_service.build_draw_event_for_seat = lambda gid, seat: [_make_draw_event(seat=0, tile_id=42)]
        manager._game_service.get_awaiting = lambda gid: awaiting
        manager.leave_game(conns[0], notify_player=False)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, game_id="game1", session_token=alice_token)
        assert [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]] == []
        assert game_of(manager).at_seat(0).timer.task is None


class TestReconnectEdgeCases:
    @pytest.mark.asyncio
    async def test_reconnect__when_session_token_still_active__should_return_already_active_error(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_token = participant_of(manager, alice_conn).ticket
        manager.leave_game(alice_conn, notify_player=False)

        bob_conn = conns[1]
        manager.reconnect(bob_conn, game_id="game1", session_token=alice_token)
        error_msgs = [m for m in bob_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        reconnect_errors = [m for m in error_msgs if m["code"] == SessionErrorCode.RECONNECT_ALREADY_ACTIVE]
        assert len(reconnect_errors) == 1

    @pytest.mark.asyncio
    async def test_reconnect__when_snapshot_raises__should_fail_the_game(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        alice_token = participant_of(manager, conns[0]).ticket
        manager.leave_game(conns[0], notify_player=False)

        def raise_error(gid, seat):
            raise RuntimeError("snapshot failed")

        manager._game_service.build_reconnection_snapshot = raise_error
        new_conn = MockConnection(game_id="game1")
        router.handle_connect(new_conn)

        router.handle_message(new_conn, {"t": WireClientMessageType.RECONNECT, "game_ticket": alice_token})
        assert new_conn.connection_id not in manager._connections
        router.handle_disconnect(new_conn)
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert (new_conn._close_code, new_conn._close_reason) == (1011, "internal_error")
        assert (conns[1]._close_code, conns[1]._close_reason) == (1011, "internal_error")


class TestReconnectToEndedGame:
    async def test_reconnect__when_game_ended_while_player_was_away__should_refuse_with_no_session(self, seeded_engine):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = participant_of(manager, conns[0]).seat
        bob_token = participant_of(manager, conns[1]).ticket
        manager.leave_game(conns[1], notify_player=False)
        arrange_final_discard(runtime_of(manager), seat=alice_seat)
        run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=alice_seat)
        assert manager.get_game("game1") is None

        reconnecting = MockConnection()
        manager.register_connection(reconnecting)
        manager.reconnect(reconnecting, game_id="game1", session_token=bob_token)
        assert [m["code"] for m in reconnecting.sent_messages] == [SessionErrorCode.RECONNECT_NO_SESSION]


class TestReconnectToPendingGame:
    async def test_reconnect__when_game_not_started_yet__should_answer_retry_later(self, seeded_engine):
        manager = make_session_manager(seeded_engine)
        specs = [
            PlayerSpec(name=name, user_id=f"user-{name}", game_ticket=f"ticket-{name}") for name in ("A", "B", "C")
        ]
        manager.create_pending_game(game_id="game1", player_specs=specs)
        joined = []
        for spec in specs[:2]:
            conn = MockConnection()
            manager.register_connection(conn)
            manager.join_game(conn, game_id="game1", session_token=spec.game_ticket)
            joined.append(conn)

        manager.leave_game(joined[0], notify_player=False)
        manager.unregister_connection(joined[0])

        before_start = MockConnection()
        manager.register_connection(before_start)
        manager.reconnect(before_start, game_id="game1", session_token="ticket-A")
        assert [m["code"] for m in before_start.sent_messages] == [SessionErrorCode.RECONNECT_RETRY_LATER]
        assert manager.get_playing_game_id("user-A") == "game1"

        await manager.shutdown()


class TestReconnectThenPlay:
    @pytest.mark.asyncio
    async def test_reconnect__when_discard_sent_after_reconnect__should_handle_it_as_reconnected_player(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]

        snapshot = _make_snapshot("game1", seat=0)
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        new_conn, _new_token = disconnect_and_reconnect(manager, alice_conn, game_id="game1")
        new_conn._outbox.clear()

        manager.handle_game_action(
            new_conn, action=GameAction.DISCARD, data={"tile_id": 1}, wait_id=current_wait_id(manager)
        )
        action_msgs = [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(action_msgs) == 1
        assert action_msgs[0]["seat"] == 0
        assert action_msgs[0]["action"] == GameAction.DISCARD
