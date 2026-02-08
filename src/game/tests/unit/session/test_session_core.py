from game.logic.enums import CallType, GameAction, MeldCallType
from game.logic.events import (
    CallPromptEvent,
    EventType,
    SeatTarget,
    ServiceEvent,
    TurnEvent,
)
from game.logic.types import MeldCaller
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.session.models import Player
from game.tests.mocks import MockConnection


class TestSessionManager:
    async def test_second_player_notifies_first(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        # conn1 should have received: game_joined + player_joined + game_started
        player_joined_msgs = [
            m for m in conn1.sent_messages if m.get("type") == SessionMessageType.PLAYER_JOINED
        ]
        assert len(player_joined_msgs) == 1
        assert player_joined_msgs[0]["player_name"] == "Bob"

    async def test_leave_game_notifies_others(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        # clear previous messages
        conn1._outbox.clear()

        await manager.leave_game(conn2)

        assert len(conn1.sent_messages) == 1
        assert conn1.sent_messages[0]["type"] == SessionMessageType.PLAYER_LEFT
        assert conn1.sent_messages[0]["player_name"] == "Bob"

    async def test_join_started_game_error(self, manager):
        connections = [MockConnection() for _ in range(5)]
        for conn in connections:
            manager.register_connection(conn)
        manager.create_game("game1", num_bots=0)

        # join 4 players, game starts automatically
        for i, conn in enumerate(connections[:4]):
            await manager.join_game(conn, "game1", f"Player{i}")

        # 5th player should get error since game already started
        await manager.join_game(connections[4], "game1", "Player4")

        msg = connections[4].sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.GAME_STARTED

    async def test_game_full_error(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        conn3 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.register_connection(conn3)
        # num_bots=2 means only 2 humans needed
        manager.create_game("game1", num_bots=2)

        game = manager.get_game("game1")
        # directly inject 2 players to fill capacity without triggering start
        game.players["fake1"] = Player(connection=conn1, name="Fake1", game_id="game1")
        game.players["fake2"] = Player(connection=conn2, name="Fake2", game_id="game1")

        # 3rd player gets game_full (game hasn't started, but at capacity)
        await manager.join_game(conn3, "game1", "Player2")

        msg = conn3.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.GAME_FULL

    async def test_duplicate_name_error(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Alice")

        msg = conn2.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.NAME_TAKEN

    async def test_empty_game_is_cleaned_up(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")
        assert manager.get_game("game1") is not None

        await manager.leave_game(conn)
        assert manager.get_game("game1") is None

    async def test_join_nonexistent_game_returns_error(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_game(conn, "nonexistent", "Alice")

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.GAME_NOT_FOUND

    async def test_handle_game_action_broadcasts_events(self, manager):
        """handle_game_action processes list of events and broadcasts them."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        await manager.handle_game_action(conn, GameAction.DISCARD, {"key": "value"})

        # mock service returns one event with target "all"
        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == EventType.DRAW
        assert msg["action"] == GameAction.DISCARD

    async def test_targeted_events_only_sent_to_target_player(self, manager):
        """Events with seat_N target go only to the player at that seat."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        # manually broadcast a seat-targeted event
        game = manager.get_game("game1")
        seat_event = ServiceEvent(
            event=EventType.TURN,
            data=TurnEvent(
                current_seat=0,
                available_actions=[],
                wall_count=70,
                target="seat_0",
            ),
            target=SeatTarget(seat=0),
        )
        await manager._broadcast_events(game, [seat_event])

        # only conn1 (seat 0) should receive the event
        assert len(conn1.sent_messages) == 1
        assert len(conn2.sent_messages) == 0

    async def test_broadcast_events_sends_all_target_to_everyone(self, manager):
        """Events with 'all' target are broadcast to all players."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        # perform action that generates broadcast event
        await manager.handle_game_action(conn1, GameAction.DISCARD, {})

        # both players should receive the event
        assert len(conn1.sent_messages) == 1
        assert len(conn2.sent_messages) == 1
        assert conn1.sent_messages[0]["type"] == EventType.DRAW
        assert conn1.sent_messages[0]["action"] == GameAction.DISCARD
        assert conn2.sent_messages[0]["type"] == EventType.DRAW
        assert conn2.sent_messages[0]["action"] == GameAction.DISCARD

    async def test_call_prompt_only_sent_to_callers(self, manager):
        """Per-seat CallPromptEvent is only sent to the targeted seat, not to all players."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

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
        assert len(conn1.sent_messages) == 1
        assert conn1.sent_messages[0]["type"] == EventType.CALL_PROMPT
        assert len(conn2.sent_messages) == 0

    async def test_call_prompt_sent_once_when_player_has_multiple_meld_options(self, manager):
        """Per-seat CallPromptEvent is sent once per player even when they have both pon and chi options."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        # seat 0 can both pon and chi the same tile — two MeldCaller entries for the same seat.
        # convert_events deduplicates and produces a single per-seat ServiceEvent.
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
        assert len(conn1.sent_messages) == 1
        assert conn1.sent_messages[0]["type"] == EventType.CALL_PROMPT
        # seat 1 (Bob) should not receive it
        assert len(conn2.sent_messages) == 0
