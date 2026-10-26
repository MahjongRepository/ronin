from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from lobby.rooms.manager import LobbyRoomManager
from lobby.tests.conftest import make_player

if TYPE_CHECKING:
    from lobby.rooms.models import LobbyRoom


def _join(mgr: LobbyRoomManager, *, room_id: str, connection_id: str, user_id: str, username: str) -> LobbyRoom | str:
    return mgr.join_room(
        room_id=room_id, player=make_player(connection_id=connection_id, user_id=user_id, username=username)
    )


def _seated_connections(room: LobbyRoom) -> list[str | None]:
    return [None if member is None else member.player.connection_id for member in room.seats]


def _host_connection(room: LobbyRoom) -> str | None:
    host = room.host
    return None if host is None else host.player.connection_id


class TestCreateRoom:
    def test_room_manager_create_room__should_register_room_with_empty_seats(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        assert room is not None
        assert mgr.get_room("room-1") is room
        assert _seated_connections(room) == [None, None, None, None]
        assert room.num_ai_players == 4


class TestJoinRoom:
    def test_room_manager_join_room__when_first_player__should_assign_seat_zero_and_ownership(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")

        result = _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")
        assert result is mgr.get_room("room-1")
        assert result.seat_of("conn-1") == 0
        assert result.is_host("conn-1") is True

    def test_room_manager_join_room__when_second_player__should_take_seat_one(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")

        room = _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        assert room.seat_of("conn-2") == 1
        assert room.is_host("conn-2") is False

    def test_room_manager_join_room__when_seat_freed__should_fill_first_open_seat(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-0", user_id="u0", username="P0")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="u1", username="P1")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="u2", username="P2")

        mgr.leave_room("room-1", "conn-1")
        _join(mgr, room_id="room-1", connection_id="conn-3", user_id="u3", username="P3")
        room = mgr.get_room("room-1")
        assert room.seat_of("conn-3") == 1

    def test_room_manager_join_room__when_room_missing__should_return_room_not_found(self):
        mgr = LobbyRoomManager()
        result = _join(mgr, room_id="no-room", connection_id="conn-1", user_id="user-1", username="Alice")
        assert result == "room_not_found"

    def test_room_manager_join_room__when_room_full__should_return_room_full(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        for i in range(4):
            _join(mgr, room_id="room-1", connection_id=f"conn-{i}", user_id=f"user-{i}", username=f"P{i}")

        result = _join(mgr, room_id="room-1", connection_id="conn-5", user_id="user-5", username="P5")
        assert result == "room_full"

    def test_room_manager_join_room__when_occupancy_reports_a_conflict__should_return_it_without_seating(self):
        mgr = LobbyRoomManager(find_conflict=lambda user_id: "already_in_queue" if user_id == "queued-user" else None)
        room = mgr.create_room("room-1")

        result = _join(mgr, room_id="room-1", connection_id="conn-1", user_id="queued-user", username="Alice")
        assert result == "already_in_queue"
        assert room.is_empty

    def test_room_manager_join_room__when_room_transitioning__should_return_room_transitioning(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        room.transitioning = True

        result = _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")
        assert result == "room_transitioning"

    def test_room_manager_join_room__when_owner_alone__should_report_can_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")

        room = _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")
        assert room.can_start is True

    def test_room_manager_join_room__when_min_human_players_unmet__should_report_cannot_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", min_human_players=4)

        room = _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")
        assert room.can_start is False


class TestMinHumanPlayers:
    def test_room_manager_can_start__when_min_human_players_reached__should_become_true(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", min_human_players=4)

        # Join 3 players — can_start stays False
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        mgr.set_ready("room-1", "conn-2", ready=True)
        _join(mgr, room_id="room-1", connection_id="conn-3", user_id="user-3", username="Carol")
        mgr.set_ready("room-1", "conn-3", ready=True)
        room = mgr.get_room("room-1")
        assert room.can_start is False

        # 4th player joins and readies — can_start becomes True
        _join(mgr, room_id="room-1", connection_id="conn-4", user_id="user-4", username="Dave")
        mgr.set_ready("room-1", "conn-4", ready=True)
        assert room.can_start is True

    def test_room_manager_can_start__when_player_not_ready__should_stay_false(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", min_human_players=2)

        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        # Bob is not ready
        room = mgr.get_room("room-1")
        assert room.can_start is False

    def test_room_manager_start_game__when_min_human_players_unmet__should_return_not_all_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1", min_human_players=2)
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")

        # Only 1 of 2 required humans
        result = mgr.start_game("room-1", "conn-1")
        assert result == "not_all_ready"


class TestLeaveRoom:
    def test_room_manager_leave_room__should_free_only_leavers_seat(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")

        mgr.leave_room("room-1", "conn-1")
        room = mgr.get_room("room-1")
        assert room is not None
        assert _seated_connections(room) == [None, "conn-2", None, None]

    def test_room_manager_leave_room__when_last_player__should_remove_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")

        mgr.leave_room("room-1", "conn-1")
        assert mgr.get_room("room-1") is None

    def test_room_manager_leave_room__when_not_in_room__should_return_false(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")

        assert mgr.leave_room("room-1", "conn-none") is False

    def test_room_manager_leave_room__when_host_leaves__should_transfer_host(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        _join(mgr, room_id="room-1", connection_id="older", user_id="user-3", username="Carol")
        mgr.leave_room("room-1", "conn-2")
        _join(mgr, room_id="room-1", connection_id="later", user_id="user-4", username="Dave")
        room = mgr.get_room("room-1")
        assert _host_connection(room) == "conn-1"
        assert _seated_connections(room) == ["conn-1", "later", "older", None]

        mgr.leave_room("room-1", "conn-1")
        assert _host_connection(room) == "older"

    def test_room_manager_leave_room__when_transitioning__should_hold_seat_until_start_fails(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        mgr.set_ready("room-1", "conn-2", ready=True)
        mgr.start_game("room-1", "conn-1")

        mgr.leave_room("room-1", "conn-2")
        assert _seated_connections(room) == ["conn-1", "conn-2", None, None]
        assert room.member("conn-2").departed is True

        mgr.clear_transitioning("room-1")
        assert _seated_connections(room) == ["conn-1", None, None, None]
        assert room.has_user("user-2") is False


class TestSetReady:
    def test_room_manager_set_ready__when_all_ready__should_return_can_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")

        result = mgr.set_ready("room-1", "conn-2", ready=True)
        assert result is mgr.get_room("room-1")
        assert result.can_start is True

    def test_room_manager_set_ready__when_another_player_not_ready__should_return_cannot_start(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        _join(mgr, room_id="room-1", connection_id="conn-3", user_id="user-3", username="Carol")

        result = mgr.set_ready("room-1", "conn-2", ready=True)
        assert result.can_start is False

    def test_room_manager_set_ready__should_not_set_transitioning(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")

        mgr.set_ready("room-1", "conn-2", ready=True)
        room = mgr.get_room("room-1")
        assert room.transitioning is False

    def test_room_manager_set_ready__when_owner__should_return_owner_cannot_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")

        result = mgr.set_ready("room-1", "conn-1", ready=True)
        assert result == "owner_cannot_ready"

    def test_room_manager_set_ready__when_not_in_room__should_return_not_in_room(self):
        mgr = LobbyRoomManager()
        result = mgr.set_ready("room-1", "conn-none", ready=True)
        assert result == "not_in_room"

    def test_room_manager_set_ready__when_room_transitioning__should_return_room_transitioning(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        room.transitioning = True

        result = mgr.set_ready("room-1", "conn-2", ready=True)
        assert result == "room_transitioning"

    def test_room_manager_set_ready__when_room_removed__should_return_not_in_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        mgr._rooms.pop("room-1")

        result = mgr.set_ready("room-1", "conn-2", ready=True)
        assert result == "not_in_room"

    def test_room_manager_set_ready__when_player_removed__should_return_not_in_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        mgr.leave_room("room-1", "conn-2")

        result = mgr.set_ready("room-1", "conn-2", ready=True)
        assert result == "not_in_room"


class TestStartGame:
    def test_room_manager_start_game__when_owner__should_start_and_set_transitioning(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")

        # Owner alone with default min_human_players=1 — can_start is True
        result = mgr.start_game("room-1", "conn-1")
        assert result is None
        room = mgr.get_room("room-1")
        assert room.transitioning is True

    def test_room_manager_start_game__when_not_owner__should_return_not_owner(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        mgr.set_ready("room-1", "conn-2", ready=True)

        result = mgr.start_game("room-1", "conn-2")
        assert result == "not_owner"

    def test_room_manager_start_game__when_player_not_ready__should_return_not_all_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        # Bob is not ready

        result = mgr.start_game("room-1", "conn-1")
        assert result == "not_all_ready"

    def test_room_manager_start_game__when_not_in_room__should_return_not_in_room(self):
        mgr = LobbyRoomManager()
        result = mgr.start_game("room-1", "conn-none")
        assert result == "not_in_room"

    def test_room_manager_start_game__when_room_transitioning__should_return_room_transitioning(self):
        mgr = LobbyRoomManager()
        room = mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")
        room.transitioning = True

        result = mgr.start_game("room-1", "conn-1")
        assert result == "room_transitioning"

    def test_room_manager_start_game__when_all_humans_ready__should_fill_remaining_seats_with_bots(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        _join(mgr, room_id="room-1", connection_id="conn-3", user_id="user-3", username="Carol")
        mgr.set_ready("room-1", "conn-2", ready=True)
        mgr.set_ready("room-1", "conn-3", ready=True)

        result = mgr.start_game("room-1", "conn-1")
        assert result is None
        room = mgr.get_room("room-1")
        assert room.transitioning is True
        assert room.num_ai_players == 1  # 3 humans, 1 bot

    def test_room_manager_start_game__when_room_removed__should_return_not_in_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")
        mgr._rooms.pop("room-1")

        result = mgr.start_game("room-1", "conn-1")
        assert result == "not_in_room"


class TestClearTransitioning:
    def test_room_manager_clear_transitioning__should_reset_transitioning_and_ready(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Owner")
        _join(mgr, room_id="room-1", connection_id="conn-2", user_id="user-2", username="Bob")
        mgr.set_ready("room-1", "conn-2", ready=True)

        mgr.start_game("room-1", "conn-1")
        room = mgr.get_room("room-1")
        assert room.transitioning is True

        mgr.clear_transitioning("room-1")
        assert room.transitioning is False
        assert room.member("conn-2").ready is False

    def test_room_manager_clear_transitioning__when_host_and_guest_left_through_the_manager__should_drop_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="host", user_id="user-1", username="Alice")
        _join(mgr, room_id="room-1", connection_id="guest", user_id="user-2", username="Bob")
        mgr.set_ready("room-1", "guest", ready=True)
        mgr.start_game("room-1", "host")
        mgr.leave_room("room-1", "guest")
        mgr.leave_room("room-1", "host")
        assert mgr.get_room("room-1") is not None

        mgr.clear_transitioning("room-1")
        assert mgr.get_room("room-1") is None

    def test_room_manager_clear_transitioning__when_room_missing__should_not_raise(self):
        mgr = LobbyRoomManager()
        mgr.clear_transitioning("nonexistent")


class TestGetRoomsInfo:
    def test_room_manager_get_rooms_info__should_describe_room(self):
        mgr = LobbyRoomManager()
        mgr.create_room("room-1")
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")

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
        _join(mgr, room_id="room-1", connection_id="conn-1", user_id="user-1", username="Alice")

        mgr.remove_room("room-1")
        assert mgr.get_room("room-1") is None


class TestRoomReaper:
    def test_room_manager_reaper__when_room_expired__should_remove_room_and_close_its_players(self):
        mgr = LobbyRoomManager(room_ttl_seconds=0)
        mgr.create_room("room-1")
        player = make_player(connection_id="conn-1", user_id="user-1", username="Alice")
        mgr.join_room(room_id="room-1", player=player)

        mgr._reap_expired_rooms()
        assert mgr.get_room("room-1") is None
        player.connection.close.assert_called_once_with(code=4002, reason="room_expired")

    def test_room_manager_reaper__when_room_transitioning__should_keep_room(self):
        mgr = LobbyRoomManager(room_ttl_seconds=0)
        room = mgr.create_room("room-1")
        room.transitioning = True

        mgr._reap_expired_rooms()
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

    async def test_room_manager_reaper__when_a_tick_raises__should_log_and_keep_reaping(self, monkeypatch, caplog):
        mgr = LobbyRoomManager(room_ttl_seconds=0, reaper_interval_seconds=0)
        second_tick = asyncio.Event()
        tick_count = 0

        def failing_first_tick():
            nonlocal tick_count
            tick_count += 1
            if tick_count == 1:
                raise RuntimeError("tick failed")

            second_tick.set()

        monkeypatch.setattr(mgr, "_reap_expired_rooms", failing_first_tick)
        mgr.start_reaper()
        await asyncio.wait_for(second_tick.wait(), timeout=1)
        await mgr.stop_reaper()

        assert "room reaper tick failed" in caplog.text
