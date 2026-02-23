"""Tests for LobbyRoomManager."""

import pytest

from lobby.rooms.manager import LobbyRoomManager


class TestLobbyRoomManager:
    def test_create_room(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1", num_ai_players=2)
        assert room.room_id == "room-1"
        assert room.num_ai_players == 2
        assert mgr.get_room("room-1") is not None

    def test_join_room_success(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=3)
        result = mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        assert isinstance(result, dict)
        assert result["type"] == "room_joined"
        assert result["room_id"] == "room-1"
        assert result["player_name"] == "Alice"
        assert len(result["players"]) == 1
        assert result["num_ai_players"] == 3

    def test_join_room_not_found(self):
        mgr = LobbyRoomManager()
        result = mgr.join_room("conn-1", "no-room", "user-1", "Alice")
        assert result == "room_not_found"

    def test_join_room_full(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=3)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        result = mgr.join_room("conn-2", "room-1", "user-2", "Bob")
        assert result == "room_full"

    def test_join_room_duplicate_user(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=2)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        result = mgr.join_room("conn-2", "room-1", "user-1", "Alice2")
        assert result == "already_in_room"

    def test_join_room_transitioning(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1", num_ai_players=3)
        room.transitioning = True
        result = mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        assert result == "room_transitioning"

    def test_leave_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=2)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")

        room_id = mgr.leave_room("conn-1")
        assert room_id == "room-1"
        room = mgr.get_room("room-1")
        assert room is not None
        assert room.player_count == 1

    def test_leave_room_removes_empty_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=3)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")

        mgr.leave_room("conn-1")
        assert mgr.get_room("room-1") is None

    def test_leave_room_not_in_room(self):
        mgr = LobbyRoomManager()
        result = mgr.leave_room("conn-none")
        assert result is None

    def test_leave_room_transfers_host(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=1)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")

        room = mgr.get_room("room-1")
        assert room.host_connection_id == "conn-1"

        mgr.leave_room("conn-1")
        room = mgr.get_room("room-1")
        assert room.host_connection_id == "conn-2"

    def test_set_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=3)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")

        result = mgr.set_ready("conn-1", ready=True)
        assert isinstance(result, tuple)
        room_id, all_ready = result
        assert room_id == "room-1"
        assert all_ready is True  # 1 player needed, 1 ready

    def test_set_ready_not_all_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=2)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")

        result = mgr.set_ready("conn-1", ready=True)
        _, all_ready = result
        assert all_ready is False

    def test_set_ready_all_ready_sets_transitioning(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=2)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")
        mgr.set_ready("conn-1", ready=True)
        result = mgr.set_ready("conn-2", ready=True)
        _, all_ready = result
        assert all_ready is True
        room = mgr.get_room("room-1")
        assert room.transitioning is True

    def test_set_ready_not_in_room(self):
        mgr = LobbyRoomManager()
        result = mgr.set_ready("conn-none", ready=True)
        assert result == "not_in_room"

    def test_set_ready_while_transitioning(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1", num_ai_players=3)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        room.transitioning = True
        result = mgr.set_ready("conn-1", ready=True)
        assert result == "room_transitioning"

    def test_clear_transitioning(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=3)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        mgr.set_ready("conn-1", ready=True)

        room = mgr.get_room("room-1")
        assert room.transitioning is True

        mgr.clear_transitioning("room-1")
        assert room.transitioning is False
        assert room.players["conn-1"].ready is False

    def test_get_rooms_info(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=3)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")

        info = mgr.get_rooms_info()
        assert len(info) == 1
        assert info[0]["room_id"] == "room-1"
        assert info[0]["player_count"] == 1
        assert info[0]["players_needed"] == 1
        assert info[0]["players"] == ["Alice"]

    def test_get_rooms_info_excludes_transitioning(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=3)
        mgr.create_room("room-2", num_ai_players=3)

        room1 = mgr.get_room("room-1")
        assert room1 is not None
        room1.transitioning = True

        info = mgr.get_rooms_info()
        assert len(info) == 1
        assert info[0]["room_id"] == "room-2"

    def test_remove_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=3)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")

        mgr.remove_room("room-1")
        assert mgr.get_room("room-1") is None

    def test_leave_room_when_room_already_removed(self):
        """leave_room when room was externally removed but connection still tracked."""
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=3)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        # Simulate external room removal
        mgr._rooms.pop("room-1")
        result = mgr.leave_room("conn-1")
        assert result == "room-1"

    def test_set_ready_room_gone(self):
        """set_ready when room is gone but connection is still tracked."""
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=3)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        mgr._rooms.pop("room-1")
        result = mgr.set_ready("conn-1", ready=True)
        assert result == "not_in_room"

    def test_set_ready_player_gone(self):
        """set_ready when player is not in room.players but connection is tracked."""
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", num_ai_players=3)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        room = mgr.get_room("room-1")
        assert room is not None
        room.players.pop("conn-1")
        result = mgr.set_ready("conn-1", ready=True)
        assert result == "not_in_room"

    def test_clear_transitioning_nonexistent_room(self):
        mgr = LobbyRoomManager()
        # Should not raise
        mgr.clear_transitioning("nonexistent")

    @pytest.mark.asyncio
    async def test_reap_callback_exception_handled(self):
        """Exception in on_room_expired callback is suppressed."""

        async def bad_callback(room_id, conn_ids):
            raise RuntimeError("callback failed")

        mgr = LobbyRoomManager(room_ttl_seconds=0, on_room_expired=bad_callback)
        mgr.create_room("room-1", num_ai_players=3)
        # Should not raise
        await mgr._reap_expired_rooms()
        assert mgr.get_room("room-1") is None


class TestRoomReaper:
    @pytest.mark.asyncio
    async def test_reap_expired_rooms(self):
        expired_rooms = []

        async def on_expired(room_id, conn_ids):
            expired_rooms.append((room_id, conn_ids))

        mgr = LobbyRoomManager(room_ttl_seconds=0, on_room_expired=on_expired)
        mgr.create_room("room-1", num_ai_players=3)
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")

        await mgr._reap_expired_rooms()

        assert mgr.get_room("room-1") is None
        assert len(expired_rooms) == 1
        assert expired_rooms[0] == ("room-1", ["conn-1"])

    @pytest.mark.asyncio
    async def test_reap_skips_transitioning_rooms(self):
        mgr = LobbyRoomManager(room_ttl_seconds=0)
        room = mgr.create_room("room-1", num_ai_players=3)
        room.transitioning = True

        await mgr._reap_expired_rooms()

        assert mgr.get_room("room-1") is not None

    @pytest.mark.asyncio
    async def test_start_stop_reaper(self):
        mgr = LobbyRoomManager(room_ttl_seconds=300)
        mgr.start_reaper()
        assert mgr._reaper_task is not None

        await mgr.stop_reaper()
        assert mgr._reaper_task is None

    @pytest.mark.asyncio
    async def test_start_reaper_idempotent(self):
        mgr = LobbyRoomManager(room_ttl_seconds=300)
        mgr.start_reaper()
        first_task = mgr._reaper_task
        mgr.start_reaper()  # should be no-op
        assert mgr._reaper_task is first_task
        await mgr.stop_reaper()
