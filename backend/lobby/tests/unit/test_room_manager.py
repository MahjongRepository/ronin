import pytest

from lobby.rooms.manager import LobbyRoomManager


class TestCreateRoom:
    def test_room_manager_create_room__should_register_room_with_empty_seats(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        assert room is not None
        assert mgr.get_room("room-1") is room
        assert room.seats == [None, None, None, None]
        assert room.num_ai_players == 4


class TestJoinRoom:
    def test_room_manager_join_room__when_first_player__should_assign_seat_zero_and_ownership(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        result = mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        assert isinstance(result, dict)
        assert result["type"] == "room_joined"
        assert result["room_id"] == "room-1"
        assert result["player_name"] == "Alice"
        assert result["is_owner"] is True
        assert len(result["players"]) == 4  # always 4 seats

        room = mgr.get_room("room-1")
        assert room.seats[0] == "conn-1"
        assert room.seat_of("conn-1") == 0

    def test_room_manager_join_room__when_second_player__should_take_seat_one(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        result = mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")
        assert isinstance(result, dict)
        assert result["is_owner"] is False

        room = mgr.get_room("room-1")
        assert room.seats[1] == "conn-2"

    def test_room_manager_join_room__when_seat_freed__should_fill_first_open_seat(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-0", room_id="room-1", user_id="u0", username="P0")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="u1", username="P1")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="u2", username="P2")

        mgr.leave_room("conn-1")  # frees seat 1
        mgr.join_room(connection_id="conn-3", room_id="room-1", user_id="u3", username="P3")

        room = mgr.get_room("room-1")
        assert room.seats[1] == "conn-3"  # filled the gap

    def test_room_manager_join_room__when_room_missing__should_return_room_not_found(self):
        mgr = LobbyRoomManager()
        result = mgr.join_room(connection_id="conn-1", room_id="no-room", user_id="user-1", username="Alice")
        assert result == "room_not_found"

    def test_room_manager_join_room__when_room_full__should_return_room_full(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        for i in range(4):
            mgr.join_room(connection_id=f"conn-{i}", room_id="room-1", user_id=f"user-{i}", username=f"P{i}")

        result = mgr.join_room(connection_id="conn-5", room_id="room-1", user_id="user-5", username="P5")
        assert result == "room_full"

    def test_room_manager_join_room__when_user_already_in_room__should_return_already_in_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        result = mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-1", username="Alice2")
        assert result == "already_in_room"

    def test_room_manager_join_room__when_room_transitioning__should_return_room_transitioning(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        room.transitioning = True
        result = mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        assert result == "room_transitioning"

    def test_room_manager_join_room__when_owner_alone__should_report_can_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        result = mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        assert isinstance(result, dict)
        # Owner alone with default min_human_players=1 — can_start is True
        assert result["can_start"] is True

    def test_room_manager_join_room__when_min_human_players_unmet__should_report_cannot_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", min_human_players=4)
        result = mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        assert isinstance(result, dict)
        # Only 1 of 4 required humans — can_start is False
        assert result["can_start"] is False


class TestMinHumanPlayers:
    def test_room_manager_can_start__when_min_human_players_reached__should_become_true(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", min_human_players=4)

        # Join 3 players — can_start stays False
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")
        mgr.set_ready("conn-2", ready=True)
        mgr.join_room(connection_id="conn-3", room_id="room-1", user_id="user-3", username="Carol")
        mgr.set_ready("conn-3", ready=True)

        room = mgr.get_room("room-1")
        assert room.can_start is False

        # 4th player joins and readies — can_start becomes True
        mgr.join_room(connection_id="conn-4", room_id="room-1", user_id="user-4", username="Dave")
        mgr.set_ready("conn-4", ready=True)
        assert room.can_start is True

    def test_room_manager_can_start__when_player_not_ready__should_stay_false(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", min_human_players=2)
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")
        # Bob is not ready
        room = mgr.get_room("room-1")
        assert room.can_start is False

    def test_room_manager_start_game__when_min_human_players_unmet__should_return_not_all_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", min_human_players=2)
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        # Only 1 of 2 required humans
        result = mgr.start_game("conn-1")
        assert result == "not_all_ready"


class TestLeaveRoom:
    def test_room_manager_leave_room__should_free_only_leavers_seat(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")

        mgr.leave_room("conn-1")
        room = mgr.get_room("room-1")
        assert room is not None
        assert room.seats[0] is None  # seat 0 restored to bot
        assert room.seats[1] == "conn-2"  # seat 1 unchanged

    def test_room_manager_leave_room__when_last_player__should_remove_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")

        mgr.leave_room("conn-1")
        assert mgr.get_room("room-1") is None

    def test_room_manager_leave_room__when_not_in_room__should_return_none(self):
        mgr = LobbyRoomManager()
        result = mgr.leave_room("conn-none")
        assert result is None

    def test_room_manager_leave_room__when_host_leaves__should_transfer_host(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")

        room = mgr.get_room("room-1")
        assert room.host_connection_id == "conn-1"

        mgr.leave_room("conn-1")
        room = mgr.get_room("room-1")
        assert room.host_connection_id == "conn-2"

    def test_room_manager_leave_room__when_room_already_removed__should_return_room_id(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        mgr._rooms.pop("room-1")
        result = mgr.leave_room("conn-1")
        assert result == "room-1"


class TestSetReady:
    def test_room_manager_set_ready__when_all_ready__should_return_can_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")

        result = mgr.set_ready("conn-2", ready=True)
        assert isinstance(result, tuple)
        room_id, can_start = result
        assert room_id == "room-1"
        assert can_start is True

    def test_room_manager_set_ready__when_another_player_not_ready__should_return_cannot_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")
        mgr.join_room(connection_id="conn-3", room_id="room-1", user_id="user-3", username="Carol")

        result = mgr.set_ready("conn-2", ready=True)
        _, can_start = result
        assert can_start is False  # conn-3 not ready yet

    def test_room_manager_set_ready__should_not_set_transitioning(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")

        mgr.set_ready("conn-2", ready=True)
        room = mgr.get_room("room-1")
        assert room.transitioning is False

    def test_room_manager_set_ready__when_owner__should_return_owner_cannot_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")

        result = mgr.set_ready("conn-1", ready=True)
        assert result == "owner_cannot_ready"

    def test_room_manager_set_ready__when_not_in_room__should_return_not_in_room(self):
        mgr = LobbyRoomManager()
        result = mgr.set_ready("conn-none", ready=True)
        assert result == "not_in_room"

    def test_room_manager_set_ready__when_room_transitioning__should_return_room_transitioning(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")
        room.transitioning = True
        result = mgr.set_ready("conn-2", ready=True)
        assert result == "room_transitioning"

    def test_room_manager_set_ready__when_room_removed__should_return_not_in_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")
        mgr._rooms.pop("room-1")
        result = mgr.set_ready("conn-2", ready=True)
        assert result == "not_in_room"

    def test_room_manager_set_ready__when_player_removed__should_return_not_in_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")
        room = mgr.get_room("room-1")
        assert room is not None
        room.players.pop("conn-2")
        result = mgr.set_ready("conn-2", ready=True)
        assert result == "not_in_room"


class TestStartGame:
    def test_room_manager_start_game__when_owner__should_start_and_set_transitioning(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        # Owner alone with default min_human_players=1 — can_start is True
        result = mgr.start_game("conn-1")
        assert result is None

        room = mgr.get_room("room-1")
        assert room.transitioning is True

    def test_room_manager_start_game__when_not_owner__should_return_not_owner(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")
        mgr.set_ready("conn-2", ready=True)

        result = mgr.start_game("conn-2")
        assert result == "not_owner"

    def test_room_manager_start_game__when_player_not_ready__should_return_not_all_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")
        # Bob is not ready

        result = mgr.start_game("conn-1")
        assert result == "not_all_ready"

    def test_room_manager_start_game__when_not_in_room__should_return_not_in_room(self):
        mgr = LobbyRoomManager()
        result = mgr.start_game("conn-none")
        assert result == "not_in_room"

    def test_room_manager_start_game__when_room_transitioning__should_return_room_transitioning(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        room.transitioning = True
        result = mgr.start_game("conn-1")
        assert result == "room_transitioning"

    def test_room_manager_start_game__when_all_humans_ready__should_fill_remaining_seats_with_bots(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")
        mgr.join_room(connection_id="conn-3", room_id="room-1", user_id="user-3", username="Carol")
        mgr.set_ready("conn-2", ready=True)
        mgr.set_ready("conn-3", ready=True)

        result = mgr.start_game("conn-1")
        assert result is None

        room = mgr.get_room("room-1")
        assert room.transitioning is True
        assert room.num_ai_players == 1  # 3 humans, 1 bot

    def test_room_manager_start_game__when_room_removed__should_return_not_in_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        mgr._rooms.pop("room-1")
        result = mgr.start_game("conn-1")
        assert result == "not_in_room"


class TestClearTransitioning:
    def test_room_manager_clear_transitioning__should_reset_transitioning_and_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Owner")
        mgr.join_room(connection_id="conn-2", room_id="room-1", user_id="user-2", username="Bob")
        mgr.set_ready("conn-2", ready=True)
        mgr.start_game("conn-1")

        room = mgr.get_room("room-1")
        assert room.transitioning is True

        mgr.clear_transitioning("room-1")
        assert room.transitioning is False
        assert room.players["conn-2"].ready is False

    def test_room_manager_clear_transitioning__when_room_missing__should_not_raise(self):
        mgr = LobbyRoomManager()
        mgr.clear_transitioning("nonexistent")


class TestGetRoomsInfo:
    def test_room_manager_get_rooms_info__should_describe_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")

        info = mgr.get_rooms_info()
        assert len(info) == 1
        assert info[0]["room_id"] == "room-1"
        assert info[0]["player_count"] == 1
        assert info[0]["num_ai_players"] == 3
        assert len(info[0]["players"]) == 4  # always 4 seat entries

    def test_room_manager_get_rooms_info__when_room_transitioning__should_exclude_it(self):
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
    def test_room_manager_remove_room__should_delete_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")

        mgr.remove_room("room-1")
        assert mgr.get_room("room-1") is None


class TestRoomReaper:
    @pytest.mark.asyncio
    async def test_room_manager_reaper__when_room_expired__should_remove_room_and_notify(self):
        expired_rooms = []

        async def on_expired(room_id, conn_ids):
            expired_rooms.append((room_id, conn_ids))

        mgr = LobbyRoomManager(room_ttl_seconds=0, on_room_expired=on_expired)
        mgr.create_room("room-1")
        mgr.join_room(connection_id="conn-1", room_id="room-1", user_id="user-1", username="Alice")

        await mgr._reap_expired_rooms()

        assert mgr.get_room("room-1") is None
        assert len(expired_rooms) == 1
        assert expired_rooms[0] == ("room-1", ["conn-1"])

    @pytest.mark.asyncio
    async def test_room_manager_reaper__when_room_transitioning__should_keep_room(self):
        mgr = LobbyRoomManager(room_ttl_seconds=0)
        room = mgr.create_room("room-1")
        room.transitioning = True

        await mgr._reap_expired_rooms()

        assert mgr.get_room("room-1") is not None

    @pytest.mark.asyncio
    async def test_room_manager_reaper__when_started_and_stopped__should_manage_task(self):
        mgr = LobbyRoomManager(room_ttl_seconds=300)
        mgr.start_reaper()
        assert mgr._reaper_task is not None

        await mgr.stop_reaper()
        assert mgr._reaper_task is None

    @pytest.mark.asyncio
    async def test_room_manager_reaper__when_started_twice__should_keep_first_task(self):
        mgr = LobbyRoomManager(room_ttl_seconds=300)
        mgr.start_reaper()
        first_task = mgr._reaper_task
        mgr.start_reaper()
        assert mgr._reaper_task is first_task
        await mgr.stop_reaper()

    @pytest.mark.asyncio
    async def test_room_manager_reaper__when_expiry_callback_raises__should_still_remove_room(self):
        async def bad_callback(room_id, conn_ids):
            raise RuntimeError("callback failed")

        mgr = LobbyRoomManager(room_ttl_seconds=0, on_room_expired=bad_callback)
        mgr.create_room("room-1")
        await mgr._reap_expired_rooms()
        assert mgr.get_room("room-1") is None
