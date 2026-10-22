from game.logic.enums import CallType, GameAction, MeldCallType
from game.logic.events import (
    CallPromptEvent,
    DrawEvent,
    EventType,
    SeatTarget,
    ServiceEvent,
)
from game.logic.types import MeldCaller
from game.messaging.types import SessionMessageType
from game.tests.mocks import MOCK_AWAITING
from game.wire.events import EVENT_TYPE_INT

from .helpers import create_started_game, current_wait_id


class TestSessionManager:
    async def test_leave_game__when_player_leaves__should_notify_others(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])

        manager.leave_game(conns[1])
        assert len(conns[0].sent_messages) == 1
        assert conns[0].sent_messages[0]["type"] == SessionMessageType.PLAYER_LEFT
        assert conns[0].sent_messages[0]["player_name"] == "Bob"

    async def test_handle_game_action__when_service_returns_event__should_broadcast_it(self, manager):
        conns = create_started_game(manager)

        manager.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={"key": "value"}, wait_id=current_wait_id(manager)
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
        seat_event = ServiceEvent(
            data=DrawEvent(
                seat=0,
                tile_id=42,
                available_actions=[],
                target=SeatTarget(seat=0),
            ),
        )
        manager._broadcast_events(game, [seat_event], MOCK_AWAITING)
        # only conn1 (seat 0) should receive the event
        assert len(conns[0].sent_messages) == 1
        assert len(conns[1].sent_messages) == 0

    async def test_broadcast_events__when_call_prompt_targets_seat__should_send_only_to_that_caller(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])

        # per-seat call_prompt targeting only seat 0 (Alice)
        game = manager.get_game("game1")
        call_event = ServiceEvent(
            data=CallPromptEvent(
                call_type=CallType.RON,
                tile_id=42,
                from_seat=2,
                callers=[0],
                target=SeatTarget(seat=0),
            ),
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
        call_event = ServiceEvent(
            data=CallPromptEvent(
                call_type=CallType.MELD,
                tile_id=55,
                from_seat=3,
                callers=callers,
                target=SeatTarget(seat=0),
            ),
        )
        manager._broadcast_events(game, [call_event], MOCK_AWAITING)
        # seat 0 should receive the call_prompt exactly once
        assert len(conns[0].sent_messages) == 1
        assert conns[0].sent_messages[0].get("t") == EVENT_TYPE_INT[EventType.CALL_PROMPT]
        # seat 1 (Bob) should not receive it
        assert len(conns[1].sent_messages) == 0
