import tempfile
from unittest.mock import patch

import pytest

from game.logic.events import ServiceEvent
from game.logic.settings import GameSettings
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.session.manager import SessionManager
from game.session.models import Game, Player
from game.tests.mocks import MockConnection, MockGameService


@pytest.fixture
def manager():
    game_service = MockGameService()
    return SessionManager(game_service)


class TestCreateRoom:
    """Tests for room creation."""

    def test_create_room(self, manager):
        room = manager.create_room("room1")
        assert room.room_id == "room1"
        assert room.num_ai_players == 3
        assert manager.get_room("room1") is room

    def test_create_room_with_bots(self, manager):
        room = manager.create_room("room1", num_ai_players=1)
        assert room.num_ai_players == 1

    def test_room_count(self, manager):
        assert manager.room_count == 0
        manager.create_room("room1")
        assert manager.room_count == 1
        manager.create_room("room2")
        assert manager.room_count == 2

    def test_get_room_nonexistent(self, manager):
        assert manager.get_room("nope") is None


class TestGetRoomsInfo:
    """Tests for get_rooms_info."""

    def test_empty_rooms_info(self, manager):
        assert manager.get_rooms_info() == []

    async def test_rooms_info_with_players(self, manager):
        manager.create_room("room1", num_ai_players=2)
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice", "tok-alice")

        infos = manager.get_rooms_info()
        assert len(infos) == 1
        info = infos[0]
        assert info.room_id == "room1"
        assert info.player_count == 1
        assert info.players_needed == 2
        assert info.total_seats == 4
        assert info.num_ai_players == 2
        assert info.players == ["Alice"]


class TestJoinRoom:
    """Tests for joining a room."""

    async def test_join_room_success(self, manager):
        manager.create_room("room1")
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice", "tok-alice")

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ROOM_JOINED
        assert msg["room_id"] == "room1"
        assert msg["session_token"] == "tok-alice"
        assert msg["num_ai_players"] == 3
        assert len(msg["players"]) == 1
        assert msg["players"][0]["name"] == "Alice"
        assert msg["players"][0]["ready"] is False

    async def test_join_room_notifies_others(self, manager):
        manager.create_room("room1", num_ai_players=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice", "tok-alice")
        await manager.join_room(conn2, "room1", "Bob", "tok-bob")

        # conn1 should have received: room_joined + player_joined(Bob)
        player_joined_msgs = [
            m for m in conn1.sent_messages if m.get("type") == SessionMessageType.PLAYER_JOINED
        ]
        assert len(player_joined_msgs) == 1
        assert player_joined_msgs[0]["player_name"] == "Bob"

    async def test_join_room_not_found(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "nonexistent", "Alice", "tok-alice")

        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.ROOM_NOT_FOUND

    async def test_join_room_full(self, manager):
        manager.create_room("room1", num_ai_players=3)  # needs 1 player
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice", "tok-alice")
        await manager.join_room(conn2, "room1", "Bob", "tok-bob")

        msg = conn2.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.ROOM_FULL

    async def test_join_room_already_in_room(self, manager):
        manager.create_room("room1", num_ai_players=2)
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice", "tok-alice")
        conn._outbox.clear()
        await manager.join_room(conn, "room1", "Bob", "tok-bob")

        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.ALREADY_IN_ROOM

    async def test_join_room_already_in_game(self, manager):
        # Put player in a started game via the room flow
        manager.create_room("game1", num_ai_players=3)
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "game1", "Alice", "tok-alice")
        await manager.set_ready(conn, ready=True)
        conn._outbox.clear()

        manager.create_room("room1")
        await manager.join_room(conn, "room1", "Alice", "tok-alice")

        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.ALREADY_IN_GAME

    async def test_join_room_name_taken(self, manager):
        manager.create_room("room1", num_ai_players=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice", "tok-alice")
        await manager.join_room(conn2, "room1", "Alice", "tok-alice2")

        msg = conn2.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.NAME_TAKEN

    async def test_join_room_transitioning(self, manager):
        manager.create_room("room1")
        room = manager.get_room("room1")
        room.transitioning = True

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice", "tok-alice")

        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.ROOM_TRANSITIONING


class TestLeaveRoom:
    """Tests for leaving a room."""

    async def test_leave_room_notifies_player(self, manager):
        manager.create_room("room1", num_ai_players=2)
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice", "tok-alice")
        conn._outbox.clear()
        await manager.leave_room(conn)

        assert any(m.get("type") == SessionMessageType.ROOM_LEFT for m in conn.sent_messages)

    async def test_leave_room_notifies_others(self, manager):
        manager.create_room("room1", num_ai_players=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice", "tok-alice")
        await manager.join_room(conn2, "room1", "Bob", "tok-bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        await manager.leave_room(conn2)

        player_left_msgs = [m for m in conn1.sent_messages if m.get("type") == SessionMessageType.PLAYER_LEFT]
        assert len(player_left_msgs) == 1
        assert player_left_msgs[0]["player_name"] == "Bob"

    async def test_leave_room_empty_cleanup(self, manager):
        manager.create_room("room1")
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice", "tok-alice")
        assert manager.get_room("room1") is not None

        await manager.leave_room(conn)
        assert manager.get_room("room1") is None
        assert manager.room_count == 0

    async def test_leave_room_host_reassignment(self, manager):
        manager.create_room("room1", num_ai_players=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice", "tok-alice")
        await manager.join_room(conn2, "room1", "Bob", "tok-bob")

        room = manager.get_room("room1")
        assert room.host_connection_id == conn1.connection_id

        await manager.leave_room(conn1)
        assert room.host_connection_id == conn2.connection_id

    async def test_leave_room_not_in_room_noop(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)
        # should not raise
        await manager.leave_room(conn)
        assert len(conn.sent_messages) == 0

    async def test_leave_room_no_notify(self, manager):
        manager.create_room("room1")
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice", "tok-alice")
        conn._outbox.clear()
        await manager.leave_room(conn, notify_player=False)

        # no ROOM_LEFT sent to the player
        assert not any(m.get("type") == SessionMessageType.ROOM_LEFT for m in conn.sent_messages)


class TestSetReady:
    """Tests for ready state toggle."""

    async def test_set_ready(self, manager):
        manager.create_room("room1", num_ai_players=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice", "tok-alice")
        await manager.join_room(conn2, "room1", "Bob", "tok-bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        await manager.set_ready(conn1, ready=True)

        # Both should receive ready changed
        for conn in [conn1, conn2]:
            ready_msgs = [
                m for m in conn.sent_messages if m.get("type") == SessionMessageType.PLAYER_READY_CHANGED
            ]
            assert len(ready_msgs) == 1
            assert ready_msgs[0]["player_name"] == "Alice"
            assert ready_msgs[0]["ready"] is True

    async def test_set_ready_not_in_room(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.set_ready(conn, ready=True)

        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.NOT_IN_ROOM

    async def test_set_ready_in_active_game_silent(self, manager):
        """set_ready silently ignores if player is in an active game."""
        manager.create_room("game1", num_ai_players=3)
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "game1", "Alice", "tok-alice")
        await manager.set_ready(conn, ready=True)
        conn._outbox.clear()

        await manager.set_ready(conn, ready=True)
        # should not receive error
        assert len(conn.sent_messages) == 0

    async def test_unready(self, manager):
        manager.create_room("room1", num_ai_players=2)  # needs 2 players; only 1 joins
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice", "tok-alice")
        await manager.set_ready(conn, ready=True)
        conn._outbox.clear()

        await manager.set_ready(conn, ready=False)

        ready_msgs = [
            m for m in conn.sent_messages if m.get("type") == SessionMessageType.PLAYER_READY_CHANGED
        ]
        assert len(ready_msgs) == 1
        assert ready_msgs[0]["ready"] is False


class TestRoomToGameTransition:
    """Tests for room-to-game transition when all players are ready."""

    async def test_transition_starts_game(self, manager):
        manager.create_room("room1")
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice", "tok-alice")
        conn._outbox.clear()

        await manager.set_ready(conn, ready=True)

        # should have received: player_ready_changed + game_starting + game events
        msg_types = [m["type"] for m in conn.sent_messages]
        assert SessionMessageType.PLAYER_READY_CHANGED in msg_types
        assert SessionMessageType.GAME_STARTING in msg_types

        # room should be gone
        assert manager.get_room("room1") is None
        # game should exist
        assert manager.get_game("room1") is not None

    async def test_transition_two_players(self, manager):
        manager.create_room("room1", num_ai_players=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice", "tok-alice")
        await manager.join_room(conn2, "room1", "Bob", "tok-bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        await manager.set_ready(conn1, ready=True)
        # game should not start yet (Bob not ready)
        assert manager.get_room("room1") is not None
        assert manager.get_game("room1") is None

        await manager.set_ready(conn2, ready=True)
        # game should start now
        assert manager.get_room("room1") is None
        assert manager.get_game("room1") is not None

        # both should have received game_starting
        for conn in [conn1, conn2]:
            starting_msgs = [
                m for m in conn.sent_messages if m.get("type") == SessionMessageType.GAME_STARTING
            ]
            assert len(starting_msgs) == 1

    async def test_transition_removes_room_players(self, manager):
        manager.create_room("room1")
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice", "tok-alice")
        assert manager.is_in_room(conn.connection_id)

        await manager.set_ready(conn, ready=True)
        assert not manager.is_in_room(conn.connection_id)
        assert manager.is_in_active_game(conn.connection_id)

    async def test_session_token_flows_through_transition(self, manager):
        """session_token sent at join_room is preserved in the Player after transition."""
        manager.create_room("room1")
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice", "my-token-123")
        await manager.set_ready(conn, ready=True)

        player = manager._players[conn.connection_id]
        assert player.session_token == "my-token-123"

        session = manager._session_store.get_session("my-token-123")
        assert session is not None
        assert session.player_name == "Alice"


class TestIsInRoom:
    """Tests for is_in_room check."""

    async def test_not_in_room_initially(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)
        assert not manager.is_in_room(conn.connection_id)

    async def test_in_room_after_join(self, manager):
        manager.create_room("room1")
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice", "tok-alice")
        assert manager.is_in_room(conn.connection_id)

    async def test_not_in_room_after_leave(self, manager):
        manager.create_room("room1")
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice", "tok-alice")
        await manager.leave_room(conn)
        assert not manager.is_in_room(conn.connection_id)


class TestRoomChat:
    """Tests for room chat."""

    async def test_broadcast_room_chat(self, manager):
        manager.create_room("room1", num_ai_players=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice", "tok-alice")
        await manager.join_room(conn2, "room1", "Bob", "tok-bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        await manager.broadcast_room_chat(conn1, "Hello!")

        for conn in [conn1, conn2]:
            chat_msgs = [m for m in conn.sent_messages if m.get("type") == SessionMessageType.CHAT]
            assert len(chat_msgs) == 1
            assert chat_msgs[0]["player_name"] == "Alice"
            assert chat_msgs[0]["text"] == "Hello!"

    async def test_room_chat_not_in_room(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.broadcast_room_chat(conn, "Hello!")

        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.NOT_IN_ROOM

    async def test_room_chat_room_gone(self, manager):
        """Chat is a no-op if room was removed concurrently."""
        manager.create_room("room1")
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice", "tok-alice")

        # Simulate room removal
        manager._rooms.pop("room1", None)
        conn._outbox.clear()

        await manager.broadcast_room_chat(conn, "Hello!")
        assert len(conn.sent_messages) == 0


class TestRoomEdgeCases:
    """Tests for edge cases and defensive guards."""

    async def test_leave_room_room_gone(self, manager):
        """Leave room when room was already removed."""
        manager.create_room("room1")
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice", "tok-alice")

        # Simulate room removal
        manager._rooms.pop("room1", None)
        manager._room_locks.pop("room1", None)

        await manager.leave_room(conn)
        assert not manager.is_in_room(conn.connection_id)

    async def test_set_ready_room_gone(self, manager):
        """set_ready is a no-op when room is gone."""
        manager.create_room("room1", num_ai_players=2)
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice", "tok-alice")

        manager._rooms.pop("room1", None)
        conn._outbox.clear()

        await manager.set_ready(conn, ready=True)
        # no crash and no messages sent
        assert len(conn.sent_messages) == 0

    async def test_set_ready_room_transitioning(self, manager):
        """set_ready is a no-op when room is transitioning."""
        manager.create_room("room1", num_ai_players=2)
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice", "tok-alice")

        room = manager.get_room("room1")
        room.transitioning = True
        conn._outbox.clear()

        await manager.set_ready(conn, ready=True)
        assert len(conn.sent_messages) == 0

    async def test_create_room_with_log_dir(self):
        """create_room with log_dir triggers log rotation."""
        with tempfile.TemporaryDirectory() as tmp:
            game_service = MockGameService()
            mgr = SessionManager(game_service, log_dir=tmp)
            room = mgr.create_room("room1")
            assert room.room_id == "room1"

    async def test_transition_room_to_game_guard_not_transitioning(self, manager):
        """_transition_room_to_game is a no-op when room is not transitioning."""
        manager.create_room("room1")
        room = manager.get_room("room1")
        room.transitioning = False

        await manager._transition_room_to_game("room1")
        # Room still exists
        assert manager.get_room("room1") is not None

    async def test_transition_aborted_when_player_leaves_during_transition(self, manager):
        """Transition aborts if a player leaves between set_ready and _transition_room_to_game."""
        manager.create_room("room1", num_ai_players=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        await manager.join_room(conn1, "room1", "Alice", "tok-alice")
        await manager.join_room(conn2, "room1", "Bob", "tok-bob")

        # Both ready up
        await manager.set_ready(conn1, ready=True)

        # Simulate race: mark transitioning as if set_ready decided to transition,
        # then a player leaves before _transition_room_to_game runs
        room = manager.get_room("room1")
        room.transitioning = True
        await manager.leave_room(conn2)

        # Now call _transition_room_to_game directly -- it should abort
        # because all_ready is no longer true
        await manager._transition_room_to_game("room1")

        # Room should still exist (transition aborted and reset transitioning)
        room = manager.get_room("room1")
        assert room is not None
        assert room.transitioning is False
        assert manager.get_game("room1") is None

    async def test_start_mahjong_game_aborts_if_game_removed(self, manager):
        """_start_mahjong_game is a no-op when the game was already cleaned up.

        Reproduces the ghost game race: all players disconnect between
        GameStartingMessage and _start_mahjong_game, causing leave_game to
        clean the game from _games. Without the liveness guard, _start_mahjong_game
        would recreate locks and heartbeat for a game no longer tracked.
        """
        game = Game(game_id="ghost1", num_ai_players=3)
        # Do NOT register the game in _games -- simulates it being cleaned up
        # by leave_game / _cleanup_empty_game before _start_mahjong_game runs.

        await manager._start_mahjong_game(game)

        # No lock, heartbeat, or service state should have been created
        assert "ghost1" not in manager._game_locks
        assert manager.get_game("ghost1") is None
        assert not game.started

    async def test_start_mahjong_game_aborts_if_game_removed_during_await(self, manager):
        """_start_mahjong_game cleans up if all players disconnect during start_game await.

        Covers the async race window: game exists when start_game begins,
        but leave_game removes it from _games while start_game is in progress.
        The post-await liveness check should detect this and clean up service
        state without creating locks or heartbeat tasks.
        """
        game_service = manager._game_service
        original_start_game = game_service.start_game

        async def slow_start_game(
            game_id: str,
            player_names: list[str],
            *,
            seed: float | None = None,
            settings: GameSettings | None = None,
        ) -> list[ServiceEvent]:
            """Yield control so leave_game can run and clean up the game."""
            result = await original_start_game(game_id, player_names, seed=seed, settings=settings)
            # Simulate the last player disconnecting during start_game.
            # Remove the game from _games as _cleanup_empty_game would.
            manager._games.pop(game_id, None)
            return result

        conn = MockConnection()
        manager.register_connection(conn)

        # Set up game as if room transition just completed
        game = Game(game_id="race1", num_ai_players=3)
        player = Player(connection=conn, name="Alice", session_token="tok", game_id="race1")
        game.players[conn.connection_id] = player
        manager._players[conn.connection_id] = player
        manager._games["race1"] = game

        with patch.object(game_service, "start_game", side_effect=slow_start_game):
            await manager._start_mahjong_game(game)

        # No lock, heartbeat, or service state should remain
        assert "race1" not in manager._game_locks
        # Service state should have been cleaned up by the post-await guard
        assert game_service.get_game_seed("race1") is None
