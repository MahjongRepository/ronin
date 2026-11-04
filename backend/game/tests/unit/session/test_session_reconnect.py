import time

import pytest

from game.logic.enums import GameAction, TimeoutType, WaitKind, WindName, WireMeldCallType
from game.logic.events import EventType
from game.logic.types import (
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
    arrange_exhaustive_draw,
    arrange_final_discard,
    arrange_ron_and_pon_on_a_discard,
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
from game.wire.enums import WireRoundResultType
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
        first_dealer_seat=0,
        dealer_dice=((1, 2), (3, 4)),
        riichi_stick_value=1000,
        seat=seat,
        round_wind=WindName.EAST,
        round_number=1,
        round_in_wind=1,
        current_player_seat=0,
        dora_indicators=[0],
        honba_sticks=0,
        riichi_sticks=0,
        my_tiles=[1, 2, 3],
        dice=(3, 4),
        tiles_remaining=70,
        player_states=[
            PlayerReconnectState(seat=i, score=25000, discards=[], melds=[], is_riichi=False, tile_count=13)
            for i in range(4)
        ],
        is_furiten=False,
        round_history=[],
    )


class TestSessionManagerReconnect:
    @pytest.mark.asyncio
    async def test_reconnect__when_session_disconnected__should_send_game_reconnected_and_tell_others_the_seat_is_back(
        self, manager
    ):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn, bob_conn = conns
        alice_token = participant_of(manager, alice_conn).ticket

        snapshot = _make_snapshot("game1", seat=0).model_copy(update={"is_furiten": True})
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: snapshot

        manager.disconnect(alice_conn)
        bob_conn._outbox.clear()

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, session_token=alice_token)
        reconnect_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED]
        assert len(reconnect_msgs) == 1
        assert reconnect_msgs[0]["gid"] == "game1"
        assert reconnect_msgs[0]["s"] == 0
        assert reconnect_msgs[0]["f"] is True
        assert [m for m in bob_conn.sent_messages if m.get("type") == SessionMessageType.SEAT_CONTROL] == [
            {"type": "seat_control", "s": 0}
        ]

    @pytest.mark.asyncio
    async def test_reconnect__when_another_seat_is_held_for_its_participant__should_mark_it_as_a_stand_in(
        self, manager
    ):
        alice_conn, bob_conn, _carol_conn = create_started_game(manager, player_names=["Alice", "Bob", "Carol"])
        bob_seat = participant_of(manager, bob_conn).seat
        alice_token = participant_of(manager, alice_conn).ticket
        manager._game_service.build_reconnection_snapshot = lambda gid, seat: _make_snapshot("game1", seat=0)

        manager.disconnect(bob_conn)
        manager.disconnect(alice_conn)
        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, session_token=alice_token)
        snapshot = next(m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED)
        players = {player["s"]: player for player in snapshot["p"]}
        assert players[bob_seat] == {"s": bob_seat, "nm": "AI", "ai": 0, "sr": 0}
        assert players[0] == {"s": 0, "nm": "Alice", "ai": 0}

    @pytest.mark.asyncio
    async def test_reconnect__when_token_unknown__should_return_no_session_error(self, manager):
        create_started_game(manager)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, session_token="nonexistent-token")
        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == SessionErrorCode.RECONNECT_NO_SESSION

    @pytest.mark.asyncio
    async def test_reconnect__when_game_id_differs_from_session__should_return_game_mismatch_error(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_token = participant_of(manager, alice_conn).ticket
        manager.disconnect(alice_conn)

        new_conn = MockConnection(game_id="wrong_game_id")
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, session_token=alice_token)
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

        manager.disconnect(alice_conn)
        bank_after_leave = timer._bank_seconds
        assert bank_after_leave == pytest.approx(initial_bank - 1.0, abs=0.1)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, session_token=alice.ticket)
        assert alice.connection is new_conn
        assert alice.timer._bank_seconds == bank_after_leave
        reconnected = next(m for m in new_conn.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED)
        assert reconnected["tm"]["bk"] == bank_after_leave

    async def test_bank_time__when_player_leaves_during_meld_prompt__should_charge_overtime(
        self, seeded_engine, fake_clock
    ):
        manager = make_session_manager(seeded_engine, clock=fake_clock.monotonic)
        conns = create_started_game(manager, player_names=["Alice", "Bob", "Carol"])
        alice, bob, carol = (participant_of(manager, conn) for conn in conns)
        discarded_four_pin = arrange_ron_and_pon_on_a_discard(
            runtime_of(manager), discarder=alice.seat, ron=bob.seat, pon=carol.seat
        )
        manager.handle_game_action(
            conns[0],
            action=GameAction.DISCARD,
            data={"tile_id": discarded_four_pin},
            wait_id=current_wait_id(manager, conns[0]),
        )
        assert game_of(manager).awaiting.kind == WaitKind.CALL
        assert carol.seat in game_of(manager).awaiting.seats
        fake_clock.advance(7)

        manager.disconnect(conns[2])
        assert carol.timer.bank_seconds == 18
        assert carol.timer.task is None

        await manager.shutdown()


class TestReconnectTakeover:
    async def test_reconnect__when_the_turn_seat_is_still_connected__should_take_over_its_turn_without_resetting_it(
        self, seeded_engine, fake_clock
    ):
        manager = make_session_manager(seeded_engine, clock=fake_clock.monotonic)
        old_conn, bob_conn = create_started_game(manager, player_names=["Alice", "Bob"])
        alice = participant_of(manager, old_conn)
        runtime = runtime_of(manager)
        assert runtime.state.round_state.current_player_seat == alice.seat
        awaiting = game_of(manager).awaiting
        decision_id = alice.decision_id
        deadline, bank = alice.timer.task, alice.timer.bank_seconds
        replay_lines = list(game_of(manager).replay.lines)
        fake_clock.advance(7)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, session_token=alice.ticket)
        reconnected, draw = new_conn.sent_messages
        drawn_tile = runtime.state.round_state.players[alice.seat].tiles[-1]
        assert (reconnected["type"], reconnected["wi"]) == (SessionMessageType.GAME_RECONNECTED, decision_id)
        assert "oc" not in reconnected
        assert (draw["t"], draw["d"], draw["wi"], draw["el"]) == (
            EVENT_TYPE_INT[EventType.DRAW],
            encode_draw(alice.seat, drawn_tile),
            decision_id,
            7,
        )
        assert (old_conn._close_code, old_conn._close_reason) == (4002, "replaced_by_new_connection")
        assert game_of(manager).awaiting == awaiting
        assert alice.timer.task is deadline
        assert not deadline.done()
        assert alice.timer.bank_seconds == bank
        assert not runtime.ai.is_ai_player(alice.seat)
        assert bob_conn.sent_messages == []

        state_before = runtime.state
        manager.handle_game_action(
            old_conn, action=GameAction.DISCARD, data={"tile_id": drawn_tile}, wait_id=decision_id
        )
        manager.disconnect(old_conn)
        assert runtime.state is state_before
        assert alice.connection is new_conn
        assert alice.timer.task is deadline
        assert old_conn.sent_messages == []
        assert bob_conn.sent_messages == []
        assert game_of(manager).replay.lines == replay_lines

        await manager.shutdown()

    async def test_reconnect__when_a_seat_with_an_unanswered_call_prompt_is_still_connected__should_resend_its_prompt(
        self, seeded_engine, fake_clock
    ):
        manager = make_session_manager(seeded_engine, clock=fake_clock.monotonic)
        conns = create_started_game(manager, player_names=["Alice", "Bob", "Carol"])
        alice, bob, carol = (participant_of(manager, conn) for conn in conns)
        discarded_four_pin = arrange_ron_and_pon_on_a_discard(
            runtime_of(manager), discarder=alice.seat, ron=bob.seat, pon=carol.seat
        )
        manager.handle_game_action(
            conns[0],
            action=GameAction.DISCARD,
            data={"tile_id": discarded_four_pin},
            wait_id=current_wait_id(manager, conns[0]),
        )
        prompt = game_of(manager).awaiting
        assert (prompt.kind, prompt.seats) == (WaitKind.CALL, frozenset({bob.seat, carol.seat}))
        original_prompt = next(m for m in conns[2].sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.CALL_PROMPT])
        carol_deadline = carol.timer.task
        fake_clock.advance(7)

        new_conn = MockConnection()
        manager.register_connection(new_conn)
        manager.reconnect(new_conn, session_token=carol.ticket)
        reconnected, call_prompt = new_conn.sent_messages
        assert reconnected["wi"] == original_prompt["wi"]
        assert (call_prompt["t"], call_prompt["ti"], call_prompt["cs"], call_prompt["wi"], call_prompt["el"]) == (
            EVENT_TYPE_INT[EventType.CALL_PROMPT],
            discarded_four_pin,
            carol.seat,
            original_prompt["wi"],
            7,
        )
        assert call_prompt["bk"] == 20
        assert [call["clt"] for call in call_prompt["ac"]] == [WireMeldCallType.PON]
        assert game_of(manager).awaiting == prompt
        assert carol.timer.task is carol_deadline
        assert not carol_deadline.done()

        manager.handle_game_action(new_conn, action=GameAction.PASS, data={}, wait_id=original_prompt["wi"])
        assert game_of(manager).awaiting.seats == frozenset({bob.seat})
        assert carol.timer.bank_seconds == 18

        await manager.shutdown()

    async def test_reconnect__when_taken_over_in_the_round_advance__should_send_the_owed_confirmation_and_its_wait(
        self, seeded_engine, fake_clock
    ):
        manager = make_session_manager(seeded_engine, clock=fake_clock.monotonic)
        alice_conn, bob_conn = create_started_game(manager, player_names=["Alice", "Bob"])
        alice, bob = participant_of(manager, alice_conn), participant_of(manager, bob_conn)
        arrange_exhaustive_draw(runtime_of(manager))
        drawn_tile = runtime_of(manager).state.round_state.players[alice.seat].tiles[-1]
        manager.handle_game_action(
            alice_conn,
            action=GameAction.DISCARD,
            data={"tile_id": drawn_tile},
            wait_id=current_wait_id(manager, alice_conn),
        )
        round_end = current_wait_id(manager, alice_conn)
        alice_result = next(m for m in alice_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.ROUND_END])
        bob_result = next(m for m in bob_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.ROUND_END])
        assert (alice_result["wi"], bob_result["wi"]) == (2, 1)
        manager.handle_game_action(alice_conn, action=GameAction.CONFIRM_ROUND, data={}, wait_id=round_end)
        advance = game_of(manager).awaiting
        assert (advance.kind, advance.seats) == (WaitKind.ROUND_ADVANCE, frozenset({bob.seat}))
        bob_deadline = bob.timer.task
        fake_clock.advance(4)

        owed = {}
        for participant, decision_id in ((alice, alice_result["wi"]), (bob, bob_result["wi"])):
            new_conn = MockConnection()
            manager.register_connection(new_conn)
            manager.reconnect(new_conn, session_token=participant.ticket)
            [reconnected] = new_conn.sent_messages
            assert reconnected["re"]["rt"] == WireRoundResultType.EXHAUSTIVE_DRAW
            assert reconnected["wi"] == decision_id
            owed[participant.name] = (reconnected["oc"], reconnected.get("el"), reconnected.get("at"))

        assert owed == {"Alice": (False, None, None), "Bob": (True, 4, 10)}
        assert bob.timer.task is bob_deadline

        manager.handle_game_action(bob.connection, action=GameAction.CONFIRM_ROUND, data={}, wait_id=bob_result["wi"])
        assert game_of(manager).awaiting.round_number == advance.round_number + 1

        await manager.shutdown()

    async def test_reconnect__when_the_connection_is_already_bound__should_refuse_it_and_keep_the_seat_bound(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        alice_conn, bob_conn = create_started_game(manager, player_names=["Alice", "Bob"])
        alice = participant_of(manager, alice_conn)

        manager.reconnect(bob_conn, session_token=alice.ticket)
        assert [m["code"] for m in bob_conn.sent_messages] == [SessionErrorCode.RECONNECT_ALREADY_ACTIVE]
        assert alice.connection is alice_conn
        assert not alice_conn.is_closed

        await manager.shutdown()


class TestReconnectEdgeCases:
    @pytest.mark.asyncio
    async def test_reconnect__when_session_token_still_active__should_return_already_active_error(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_conn = conns[0]
        alice_token = participant_of(manager, alice_conn).ticket
        manager.disconnect(alice_conn)

        bob_conn = conns[1]
        manager.reconnect(bob_conn, session_token=alice_token)
        error_msgs = [m for m in bob_conn.sent_messages if m.get("type") == SessionMessageType.ERROR]
        reconnect_errors = [m for m in error_msgs if m["code"] == SessionErrorCode.RECONNECT_ALREADY_ACTIVE]
        assert len(reconnect_errors) == 1

    @pytest.mark.asyncio
    async def test_reconnect__when_snapshot_raises__should_fail_the_game(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        alice_token = participant_of(manager, conns[0]).ticket
        manager.disconnect(conns[0])

        def raise_error(gid, seat):
            raise RuntimeError("snapshot failed")

        manager._game_service.build_reconnection_snapshot = raise_error
        new_conn = MockConnection()
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
        manager.disconnect(conns[1])
        arrange_final_discard(runtime_of(manager), seat=alice_seat)
        run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=alice_seat)
        assert manager.get_game("game1") is None

        reconnecting = MockConnection()
        manager.register_connection(reconnecting)
        manager.reconnect(reconnecting, session_token=bob_token)
        assert [m["code"] for m in reconnecting.sent_messages] == [SessionErrorCode.RECONNECT_NO_SESSION]


class TestReconnectDuringRoundAdvance:
    async def test_reconnect__when_round_advance_pending__should_send_round_result_and_wait_id(self, seeded_engine):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = participant_of(manager, conns[0]).seat
        bob_token = participant_of(manager, conns[1]).ticket
        bob_wait_id = current_wait_id(manager, conns[1])
        assert runtime_of(manager).state.round_state.current_player_seat == alice_seat
        manager.disconnect(conns[1])
        arrange_exhaustive_draw(runtime_of(manager))
        run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=alice_seat)
        assert game_of(manager).awaiting.kind == WaitKind.ROUND_ADVANCE

        reconnecting = MockConnection()
        manager.register_connection(reconnecting)
        manager.reconnect(reconnecting, session_token=bob_token)
        reconnected = next(
            m for m in reconnecting.sent_messages if m.get("type") == SessionMessageType.GAME_RECONNECTED
        )
        assert reconnected["re"]["rt"] == WireRoundResultType.EXHAUSTIVE_DRAW
        assert reconnected["wi"] == bob_wait_id
        assert reconnected["oc"] is False

        await manager.shutdown()


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
            manager.join_game(conn, session_token=spec.game_ticket)
            joined.append(conn)

        manager.disconnect(joined[0])

        before_start = MockConnection()
        manager.register_connection(before_start)
        manager.reconnect(before_start, session_token="ticket-A")
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
            new_conn, action=GameAction.DISCARD, data={"tile_id": 1}, wait_id=current_wait_id(manager, new_conn)
        )
        action_msgs = [m for m in new_conn.sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(action_msgs) == 1
        assert action_msgs[0]["seat"] == 0
        assert action_msgs[0]["action"] == GameAction.DISCARD
