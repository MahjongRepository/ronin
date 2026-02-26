"""Tests for LobbyRoomManager."""

import pytest

from lobby.rooms.manager import LobbyRoomManager


class TestCreateRoom:
    def test_create_room(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        assert room is not None
        assert mgr.get_room("room-1") is room
        assert room.seats == [None, None, None, None]
        assert room.num_ai_players == 4


class TestJoinRoom:
    def test_join_success_assigns_seat_zero(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        result = mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        assert isinstance(result, dict)
        assert result["type"] == "room_joined"
        assert result["room_id"] == "room-1"
        assert result["player_name"] == "Alice"
        assert result["is_owner"] is True
        assert len(result["players"]) == 4  # always 4 seats

        room = mgr.get_room("room-1")
        assert room.seats[0] == "conn-1"
        assert room.seat_of("conn-1") == 0

    def test_second_player_takes_seat_one(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        result = mgr.join_room("conn-2", "room-1", "user-2", "Bob")
        assert isinstance(result, dict)
        assert result["is_owner"] is False

        room = mgr.get_room("room-1")
        assert room.seats[1] == "conn-2"

    def test_join_fills_first_open_seat_after_leave(self):
        """After a player leaves seat 1, the next joiner takes seat 1 (not seat 3)."""
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-0", "room-1", "u0", "P0")
        mgr.join_room("conn-1", "room-1", "u1", "P1")
        mgr.join_room("conn-2", "room-1", "u2", "P2")

        mgr.leave_room("conn-1")  # frees seat 1
        mgr.join_room("conn-3", "room-1", "u3", "P3")

        room = mgr.get_room("room-1")
        assert room.seats[1] == "conn-3"  # filled the gap

    def test_join_room_not_found(self):
        mgr = LobbyRoomManager()
        result = mgr.join_room("conn-1", "no-room", "user-1", "Alice")
        assert result == "room_not_found"

    def test_join_room_full(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        for i in range(4):
            mgr.join_room(f"conn-{i}", "room-1", f"user-{i}", f"P{i}")

        result = mgr.join_room("conn-5", "room-1", "user-5", "P5")
        assert result == "room_full"

    def test_join_room_duplicate_user(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        result = mgr.join_room("conn-2", "room-1", "user-1", "Alice2")
        assert result == "already_in_room"

    def test_join_room_transitioning(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        room.transitioning = True
        result = mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        assert result == "room_transitioning"

    def test_join_response_includes_can_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        result = mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        assert isinstance(result, dict)
        # Owner alone — can_start is True
        assert result["can_start"] is True


class TestLeaveRoom:
    def test_leave_clears_correct_seat(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")

        mgr.leave_room("conn-1")
        room = mgr.get_room("room-1")
        assert room is not None
        assert room.seats[0] is None  # seat 0 restored to bot
        assert room.seats[1] == "conn-2"  # seat 1 unchanged

    def test_leave_room_removes_empty_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")

        mgr.leave_room("conn-1")
        assert mgr.get_room("room-1") is None

    def test_leave_room_not_in_room(self):
        mgr = LobbyRoomManager()
        result = mgr.leave_room("conn-none")
        assert result is None

    def test_leave_room_transfers_host(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")

        room = mgr.get_room("room-1")
        assert room.host_connection_id == "conn-1"

        mgr.leave_room("conn-1")
        room = mgr.get_room("room-1")
        assert room.host_connection_id == "conn-2"

    def test_leave_room_when_room_already_removed(self):
        """leave_room when room was externally removed but connection still tracked."""
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        mgr._rooms.pop("room-1")
        result = mgr.leave_room("conn-1")
        assert result == "room-1"


class TestSetReady:
    def test_set_ready_returns_can_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")

        result = mgr.set_ready("conn-2", ready=True)
        assert isinstance(result, tuple)
        room_id, can_start = result
        assert room_id == "room-1"
        assert can_start is True

    def test_set_ready_not_all_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")
        mgr.join_room("conn-3", "room-1", "user-3", "Carol")

        result = mgr.set_ready("conn-2", ready=True)
        _, can_start = result
        assert can_start is False  # conn-3 not ready yet

    def test_set_ready_does_not_set_transitioning(self):
        """set_ready no longer auto-triggers transition."""
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")

        mgr.set_ready("conn-2", ready=True)
        room = mgr.get_room("room-1")
        assert room.transitioning is False

    def test_owner_cannot_set_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")

        result = mgr.set_ready("conn-1", ready=True)
        assert result == "owner_cannot_ready"

    def test_set_ready_not_in_room(self):
        mgr = LobbyRoomManager()
        result = mgr.set_ready("conn-none", ready=True)
        assert result == "not_in_room"

    def test_set_ready_while_transitioning(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")
        room.transitioning = True
        result = mgr.set_ready("conn-2", ready=True)
        assert result == "room_transitioning"

    def test_set_ready_room_gone(self):
        """set_ready when room is gone but connection is still tracked."""
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")
        mgr._rooms.pop("room-1")
        result = mgr.set_ready("conn-2", ready=True)
        assert result == "not_in_room"

    def test_set_ready_player_gone(self):
        """set_ready when player is not in room.players but connection is tracked."""
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")
        room = mgr.get_room("room-1")
        assert room is not None
        room.players.pop("conn-2")
        result = mgr.set_ready("conn-2", ready=True)
        assert result == "not_in_room"


class TestStartGame:
    def test_owner_can_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        # Owner alone with 3 bots — can_start is True
        result = mgr.start_game("conn-1")
        assert result is None

        room = mgr.get_room("room-1")
        assert room.transitioning is True

    def test_non_owner_cannot_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")
        mgr.set_ready("conn-2", ready=True)

        result = mgr.start_game("conn-2")
        assert result == "not_owner"

    def test_start_game_when_not_all_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")
        # Bob is not ready

        result = mgr.start_game("conn-1")
        assert result == "not_all_ready"

    def test_start_game_not_in_room(self):
        mgr = LobbyRoomManager()
        result = mgr.start_game("conn-none")
        assert result == "not_in_room"

    def test_start_game_while_transitioning(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        room.transitioning = True
        result = mgr.start_game("conn-1")
        assert result == "room_transitioning"

    def test_start_game_with_multiple_humans_all_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")
        mgr.join_room("conn-3", "room-1", "user-3", "Carol")
        mgr.set_ready("conn-2", ready=True)
        mgr.set_ready("conn-3", ready=True)

        result = mgr.start_game("conn-1")
        assert result is None

        room = mgr.get_room("room-1")
        assert room.transitioning is True
        assert room.num_ai_players == 1  # 3 humans, 1 bot

    def test_start_game_room_gone(self):
        """start_game when room is gone but connection is still tracked."""
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        mgr._rooms.pop("room-1")
        result = mgr.start_game("conn-1")
        assert result == "not_in_room"


class TestClearTransitioning:
    def test_clear_transitioning(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Owner")
        mgr.join_room("conn-2", "room-1", "user-2", "Bob")
        mgr.set_ready("conn-2", ready=True)
        mgr.start_game("conn-1")

        room = mgr.get_room("room-1")
        assert room.transitioning is True

        mgr.clear_transitioning("room-1")
        assert room.transitioning is False
        assert room.players["conn-2"].ready is False

    def test_clear_transitioning_nonexistent_room(self):
        mgr = LobbyRoomManager()
        mgr.clear_transitioning("nonexistent")


class TestGetRoomsInfo:
    def test_get_rooms_info(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")

        info = mgr.get_rooms_info()
        assert len(info) == 1
        assert info[0]["room_id"] == "room-1"
        assert info[0]["player_count"] == 1
        assert info[0]["num_ai_players"] == 3
        assert len(info[0]["players"]) == 4  # always 4 seat entries

    def test_get_rooms_info_excludes_transitioning(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.create_room("room-2")

        room1 = mgr.get_room("room-1")
        assert room1 is not None
        room1.transitioning = True

        info = mgr.get_rooms_info()
        assert len(info) == 1
        assert info[0]["room_id"] == "room-2"


class TestRemoveRoom:
    def test_remove_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")

        mgr.remove_room("room-1")
        assert mgr.get_room("room-1") is None


class TestRoomReaper:
    @pytest.mark.asyncio
    async def test_reap_expired_rooms(self):
        expired_rooms = []

        async def on_expired(room_id, conn_ids):
            expired_rooms.append((room_id, conn_ids))

        mgr = LobbyRoomManager(room_ttl_seconds=0, on_room_expired=on_expired)
        mgr.create_room("room-1")
        mgr.join_room("conn-1", "room-1", "user-1", "Alice")

        await mgr._reap_expired_rooms()

        assert mgr.get_room("room-1") is None
        assert len(expired_rooms) == 1
        assert expired_rooms[0] == ("room-1", ["conn-1"])

    @pytest.mark.asyncio
    async def test_reap_skips_transitioning_rooms(self):
        mgr = LobbyRoomManager(room_ttl_seconds=0)
        room = mgr.create_room("room-1")
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
        mgr.start_reaper()
        assert mgr._reaper_task is first_task
        await mgr.stop_reaper()

    @pytest.mark.asyncio
    async def test_reap_callback_exception_handled(self):
        """Exception in on_room_expired callback is suppressed."""

        async def bad_callback(room_id, conn_ids):
            raise RuntimeError("callback failed")

        mgr = LobbyRoomManager(room_ttl_seconds=0, on_room_expired=bad_callback)
        mgr.create_room("room-1")
        await mgr._reap_expired_rooms()
        assert mgr.get_room("room-1") is None
