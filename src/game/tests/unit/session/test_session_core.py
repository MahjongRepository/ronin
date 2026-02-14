from game.logic.enums import CallType, GameAction, MeldCallType
from game.logic.events import (
    CallPromptEvent,
    DrawEvent,
    EventType,
    SeatTarget,
    ServiceEvent,
)
from game.logic.types import MeldCaller
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.tests.mocks import MockConnection

from .helpers import create_started_game


class TestSessionManager:
    async def test_second_player_notifies_first(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_room("game1", num_ai_players=2)

        await manager.join_room(conn1, "game1", "Alice", "tok-alice")
        await manager.join_room(conn2, "game1", "Bob", "tok-bob")

        # conn1 should have received: room_joined + player_joined(Bob)
        player_joined_msgs = [
            m for m in conn1.sent_messages if m.get("type") == SessionMessageType.PLAYER_JOINED
        ]
        assert len(player_joined_msgs) == 1
        assert player_joined_msgs[0]["player_name"] == "Bob"

    async def test_leave_game_notifies_others(self, manager):
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        await manager.leave_game(conns[1])

        assert len(conns[0].sent_messages) == 1
        assert conns[0].sent_messages[0]["type"] == SessionMessageType.PLAYER_LEFT
        assert conns[0].sent_messages[0]["player_name"] == "Bob"

    async def test_duplicate_name_error(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_room("game1", num_ai_players=2)

        await manager.join_room(conn1, "game1", "Alice", "tok-alice")
        await manager.join_room(conn2, "game1", "Alice", "tok-alice2")

        msg = conn2.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.NAME_TAKEN

    async def test_empty_game_is_cleaned_up(self, manager):
        conns = await create_started_game(manager, "game1")
        assert manager.get_game("game1") is not None

        await manager.leave_game(conns[0])
        assert manager.get_game("game1") is None

    async def test_handle_game_action_broadcasts_events(self, manager):
        """handle_game_action processes list of events and broadcasts them."""
        conns = await create_started_game(manager, "game1")

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {"key": "value"})

        # mock service returns one event with target "all"
        assert len(conns[0].sent_messages) == 1
        msg = conns[0].sent_messages[0]
        assert msg["type"] == EventType.DRAW
        assert msg["action"] == GameAction.DISCARD

    async def test_targeted_events_only_sent_to_target_player(self, manager):
        """Events with seat_N target go only to the player at that seat."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # manually broadcast a seat-targeted event
        game = manager.get_game("game1")
        seat_event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                seat=0,
                available_actions=[],
                target="seat_0",
            ),
            target=SeatTarget(seat=0),
        )
        await manager._broadcast_events(game, [seat_event])

        # only conn1 (seat 0) should receive the event
        assert len(conns[0].sent_messages) == 1
        assert len(conns[1].sent_messages) == 0

    async def test_broadcast_events_sends_all_target_to_everyone(self, manager):
        """Events with 'all' target are broadcast to all players."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # perform action that generates broadcast event
        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # both players should receive the event
        assert len(conns[0].sent_messages) == 1
        assert len(conns[1].sent_messages) == 1
        assert conns[0].sent_messages[0]["type"] == EventType.DRAW
        assert conns[0].sent_messages[0]["action"] == GameAction.DISCARD
        assert conns[1].sent_messages[0]["type"] == EventType.DRAW
        assert conns[1].sent_messages[0]["action"] == GameAction.DISCARD

    async def test_call_prompt_only_sent_to_callers(self, manager):
        """Per-seat CallPromptEvent is only sent to the targeted seat, not to all players."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # per-seat call_prompt targeting only seat 0 (Alice)
        game = manager.get_game("game1")
        call_event = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.RON,
                tile_id=42,
                from_seat=2,
                callers=[0],
                target="all",
            ),
            target=SeatTarget(seat=0),
        )
        await manager._broadcast_events(game, [call_event])

        # only conn1 (seat 0) should receive the call_prompt
        assert len(conns[0].sent_messages) == 1
        assert conns[0].sent_messages[0]["type"] == EventType.CALL_PROMPT
        assert len(conns[1].sent_messages) == 0

    async def test_call_prompt_sent_once_when_player_has_multiple_meld_options(self, manager):
        """Per-seat CallPromptEvent is sent once per player even when they have both pon and chi options."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # seat 0 can both pon and chi the same tile -- two MeldCaller entries for the same seat.
        game = manager.get_game("game1")
        callers = [
            MeldCaller(seat=0, call_type=MeldCallType.PON),
            MeldCaller(seat=0, call_type=MeldCallType.CHI, options=((57, 63),)),
        ]
        call_event = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.MELD,
                tile_id=55,
                from_seat=3,
                callers=callers,
                target="all",
            ),
            target=SeatTarget(seat=0),
        )
        await manager._broadcast_events(game, [call_event])

        # seat 0 should receive the call_prompt exactly once
        assert len(conns[0].sent_messages) == 1
        assert conns[0].sent_messages[0]["type"] == EventType.CALL_PROMPT
        # seat 1 (Bob) should not receive it
        assert len(conns[1].sent_messages) == 0
