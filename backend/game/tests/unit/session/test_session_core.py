import json
from typing import TYPE_CHECKING, Any

from game.logic.enums import CallType, GameAction, MeldCallType, WaitKind
from game.logic.events import (
    CallPromptEvent,
    EventType,
    FuritenEvent,
    SeatTarget,
)
from game.logic.tiles import NUM_TILES
from game.logic.types import MeldCaller
from game.logic.wall import tiles_remaining
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import MOCK_AWAITING
from game.tests.unit.helpers import _update_player
from game.wire.compact import encode_draw
from game.wire.enums import WireEventType
from game.wire.events import EVENT_TYPE_INT

from .helpers import (
    arrange_pon_now_and_on_the_next_draw,
    create_started_game,
    current_wait_id,
    game_of,
    participant_of,
    runtime_of,
)

if TYPE_CHECKING:
    from game.session.manager import SessionManager
    from game.tests.mocks import MockConnection

HAKU_COPIES = [tile_copies(copy, honors="5")[0] for copy in range(4)]
DRAW_MESSAGE_TYPES = (WireEventType.DRAW, WireEventType.DRAW_NOTICE)


class TestSessionManager:
    async def test_disconnect__when_player_leaves__should_tell_the_others_an_ai_player_stands_in_at_the_seat(
        self, manager
    ):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        bob_seat = participant_of(manager, conns[1]).seat

        manager.disconnect(conns[1])
        assert conns[0].sent_messages == [{"type": "seat_control", "s": bob_seat, "r": 0}]

    async def test_handle_game_action__when_service_returns_event__should_broadcast_it(self, manager):
        conns = create_started_game(manager)

        manager.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={"key": "value"}, wait_id=current_wait_id(manager, conns[0])
        )
        # mock service returns one event with target "all"
        assert len(conns[0].sent_messages) == 1
        msg = conns[0].sent_messages[0]
        assert msg.get("t") == EVENT_TYPE_INT[EventType.DRAW]
        assert msg["action"] == GameAction.DISCARD

    async def test_broadcast_events__when_event_targets_seat__should_send_only_to_that_player(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])

        # manually broadcast a seat-targeted event
        game = manager.get_game("game1")
        seat_event = FuritenEvent(is_furiten=True, target=SeatTarget(seat=0))
        manager._broadcast_events(game, [seat_event], MOCK_AWAITING)
        # only conn1 (seat 0) should receive the event
        assert len(conns[0].sent_messages) == 1
        assert len(conns[1].sent_messages) == 0

    async def test_broadcast_events__when_call_prompt_targets_seat__should_send_only_to_that_caller(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])

        # per-seat call_prompt targeting only seat 0 (Alice)
        game = manager.get_game("game1")
        call_event = CallPromptEvent(
            call_type=CallType.RON,
            tile_id=42,
            from_seat=2,
            callers=[0],
            target=SeatTarget(seat=0),
        )
        manager._broadcast_events(game, [call_event], MOCK_AWAITING)
        # only conn1 (seat 0) should receive the call_prompt
        assert len(conns[0].sent_messages) == 1
        assert conns[0].sent_messages[0].get("t") == EVENT_TYPE_INT[EventType.CALL_PROMPT]
        assert len(conns[1].sent_messages) == 0

    async def test_broadcast_events__when_caller_has_pon_and_chi__should_send_call_prompt_once(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])

        # seat 0 can both pon and chi the same tile -- two MeldCaller entries for the same seat.
        game = manager.get_game("game1")
        callers = [
            MeldCaller(seat=0, call_type=MeldCallType.PON),
            MeldCaller(seat=0, call_type=MeldCallType.CHI, options=((57, 63),)),
        ]
        call_event = CallPromptEvent(
            call_type=CallType.MELD,
            tile_id=55,
            from_seat=3,
            callers=callers,
            target=SeatTarget(seat=0),
        )
        manager._broadcast_events(game, [call_event], MOCK_AWAITING)
        # seat 0 should receive the call_prompt exactly once
        assert len(conns[0].sent_messages) == 1
        assert conns[0].sent_messages[0].get("t") == EVENT_TYPE_INT[EventType.CALL_PROMPT]
        # seat 1 (Bob) should not receive it
        assert len(conns[1].sent_messages) == 0


def _seen_draws(conn: MockConnection) -> list[dict[str, Any]]:
    return [
        {"t": message["t"], "d": message["d"], "tr": message["tr"]} if message["t"] == WireEventType.DRAW else message
        for message in conn.sent_messages
        if message.get("t") in DRAW_MESSAGE_TYPES
    ]


def _replay_lines(manager: SessionManager) -> list[dict[str, Any]]:
    return [json.loads(line) for line in game_of(manager).replay.lines]


def _discard_drawn_tile(manager: SessionManager, conns: list[MockConnection]) -> None:
    awaiting = game_of(manager).awaiting
    assert awaiting.kind == WaitKind.TURN
    [seat] = awaiting.seats
    conn = next(conn for conn in conns if participant_of(manager, conn).seat == seat)
    drawn_tile = runtime_of(manager).state.round_state.players[seat].tiles[-1]
    manager.handle_game_action(
        conn, action=GameAction.DISCARD, data={"tile_id": drawn_tile}, wait_id=current_wait_id(manager, conn)
    )


class TestDrawDelivery:
    async def test_send_events__when_humans_and_ai_players_draw__should_send_the_drawer_its_draw_and_others_a_notice(
        self, seeded_engine
    ):
        live_wall_after_deal = 70
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob"], keep_start_messages=True)
        alice, bob = (participant_of(manager, conn) for conn in conns)
        for _ in range(4):
            _discard_drawn_tile(manager, conns)

        lines = _replay_lines(manager)
        replay_draws = [line for line in lines if line["t"] == WireEventType.DRAW]
        drawers = [line["d"] // NUM_TILES for line in replay_draws]
        assert drawers[0] == alice.seat
        assert set(drawers) == {0, 1, 2, 3}
        assert WireEventType.DRAW_NOTICE not in {line["t"] for line in lines}
        assert [line["tr"] for line in replay_draws] == [
            live_wall_after_deal - drawn for drawn in range(1, len(replay_draws) + 1)
        ]
        for participant, conn in zip((alice, bob), conns, strict=True):
            expected = [
                {"t": WireEventType.DRAW, "d": line["d"], "tr": line["tr"]}
                if drawer == participant.seat
                else {"t": WireEventType.DRAW_NOTICE, "s": drawer, "tr": line["tr"]}
                for line, drawer in zip(replay_draws, drawers, strict=True)
            ]
            assert _seen_draws(conn) == expected

        await manager.shutdown()

    async def test_send_events__when_a_seat_draws_its_kan_replacement__should_send_the_others_its_notice(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        alice_conn, bob_conn = create_started_game(manager, player_names=["Alice", "Bob"])
        alice = participant_of(manager, alice_conn)
        hand = runtime_of(manager).state.round_state.players[alice.seat].tiles
        _update_player(
            runtime_of(manager),
            seat=alice.seat,
            tiles=(*[tile for tile in hand if tile not in HAKU_COPIES][:10], *HAKU_COPIES),
        )
        replay_size = len(game_of(manager).replay.lines)

        manager.handle_game_action(
            alice_conn,
            action=GameAction.CALL_KAN,
            data={"tile_id": HAKU_COPIES[0], "kan_type": "closed"},
            wait_id=current_wait_id(manager, alice_conn),
        )
        round_state = runtime_of(manager).state.round_state
        replacement = encode_draw(alice.seat, round_state.players[alice.seat].tiles[-1])
        wall_left = tiles_remaining(round_state.wall)
        assert _seen_draws(alice_conn) == [{"t": WireEventType.DRAW, "d": replacement, "tr": wall_left}]
        assert _seen_draws(bob_conn) == [{"t": WireEventType.DRAW_NOTICE, "s": alice.seat, "tr": wall_left}]
        new_lines = _replay_lines(manager)[replay_size:]
        assert [line["d"] for line in new_lines if line["t"] == WireEventType.DRAW] == [replacement]

        await manager.shutdown()

    async def test_send_events__when_a_seat_pons__should_send_nobody_a_draw_or_its_notice(self, seeded_engine):
        manager = make_session_manager(seeded_engine)
        alice_conn, bob_conn = create_started_game(manager, player_names=["Alice", "Bob"])
        alice, bob = participant_of(manager, alice_conn), participant_of(manager, bob_conn)
        discarded_four_pin = arrange_pon_now_and_on_the_next_draw(
            runtime_of(manager), discarder=alice.seat, caller=bob.seat
        )
        manager.handle_game_action(
            alice_conn,
            action=GameAction.DISCARD,
            data={"tile_id": discarded_four_pin},
            wait_id=current_wait_id(manager, alice_conn),
        )
        assert game_of(manager).awaiting.seats == frozenset({bob.seat})
        alice_conn._outbox.clear()
        bob_conn._outbox.clear()

        manager.handle_game_action(
            bob_conn,
            action=GameAction.CALL_PON,
            data={"tile_id": discarded_four_pin},
            wait_id=current_wait_id(manager, bob_conn),
        )
        assert [message["t"] for message in alice_conn.sent_messages] == [WireEventType.MELD]
        assert [message["t"] for message in bob_conn.sent_messages] == [WireEventType.MELD, WireEventType.TURN]

        await manager.shutdown()
