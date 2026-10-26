from lobby.rooms.models import BOT_NAME_PREFIX, LobbyRoom, RoomMember
from lobby.tests.conftest import make_player


def _seat(room: LobbyRoom, seat: int, connection_id: str, *, ready: bool = False) -> RoomMember:
    player = make_player(connection_id=connection_id, user_id=f"user-{connection_id}", username=connection_id)
    room.seat_player(seat, player)
    member = room.member(connection_id)
    assert member is not None
    member.ready = ready
    return member


class TestSeats:
    def test_lobby_room_first_open_seat__when_room_empty__should_return_zero(self):
        room = LobbyRoom(room_id="r1")
        assert room.first_open_seat() == 0

    def test_lobby_room_first_open_seat__when_room_full__should_return_none(self):
        room = LobbyRoom(room_id="r1")
        for i in range(4):
            _seat(room, i, f"c{i}")

        assert room.first_open_seat() is None

    def test_lobby_room_first_open_seat__when_gap_in_middle__should_return_gap(self):
        room = LobbyRoom(room_id="r1")
        for i in range(4):
            _seat(room, i, f"c{i}")

        room.vacate_seat(room.member("c1"))
        assert room.first_open_seat() == 1

    def test_lobby_room_seat_of__should_return_the_connections_seat_or_none(self):
        room = LobbyRoom(room_id="r1")
        _seat(room, 2, "conn-x")
        assert room.seat_of("conn-x") == 2
        assert room.seat_of("conn-unknown") is None

    def test_lobby_room_vacate_seat__should_not_shift_other_players(self):
        room = LobbyRoom(room_id="r1")
        for i in range(3):
            _seat(room, i, f"conn-{i}")

        room.vacate_seat(room.member("conn-1"))
        assert room.seat_of("conn-0") == 0
        assert room.seats[1] is None
        assert room.seat_of("conn-2") == 2


class TestDerivedProperties:
    def test_lobby_room_num_ai_players__when_one_human__should_be_three(self):
        room = LobbyRoom(room_id="r1")
        _seat(room, 0, "conn-1")
        assert room.num_ai_players == 3

    def test_lobby_room_is_empty__should_track_whether_anyone_is_seated(self):
        room = LobbyRoom(room_id="r1")
        assert room.is_empty is True

        _seat(room, 0, "c1")
        assert room.is_empty is False


class TestCanStart:
    def test_lobby_room_can_start__when_room_empty__should_be_false(self):
        room = LobbyRoom(room_id="r1")
        assert room.can_start is False

    def test_lobby_room_can_start__when_owner_alone__should_be_true(self):
        room = LobbyRoom(room_id="r1")
        _seat(room, 0, "conn-1")

        assert room.can_start is True

    def test_lobby_room_can_start__when_non_owner_not_ready__should_be_false(self):
        room = LobbyRoom(room_id="r1")
        _seat(room, 0, "conn-1")
        _seat(room, 1, "conn-2", ready=False)

        assert room.can_start is False

    def test_lobby_room_can_start__when_all_non_owners_ready__should_be_true(self):
        room = LobbyRoom(room_id="r1")
        _seat(room, 0, "conn-1")
        _seat(room, 1, "conn-2", ready=True)

        assert room.can_start is True

    def test_lobby_room_can_start__when_one_of_several_non_owners_not_ready__should_be_false(self):
        room = LobbyRoom(room_id="r1")
        _seat(room, 0, "conn-1")
        _seat(room, 1, "conn-2", ready=True)
        last = _seat(room, 2, "conn-3", ready=False)
        assert room.can_start is False

        last.ready = True
        assert room.can_start is True


class TestGetPlayerInfo:
    def test_lobby_room_get_player_info__when_room_empty__should_return_four_bots(self):
        room = LobbyRoom(room_id="r1")
        info = room.get_player_info()
        assert len(info) == 4
        for i, p in enumerate(info):
            assert p.is_bot is True
            assert p.ready is True
            assert p.is_owner is False
            assert p.name == f"{BOT_NAME_PREFIX} {i + 1}"

    def test_lobby_room_get_player_info__when_humans_and_bots__should_preserve_seat_order(self):
        room = LobbyRoom(room_id="r1")
        _seat(room, 0, "Alice")
        _seat(room, 2, "Bob", ready=True)

        info = room.get_player_info()
        assert len(info) == 4
        assert info[0].name == "Alice"
        assert info[0].is_bot is False
        assert info[0].is_owner is True
        assert info[0].ready is True
        assert info[1].name == f"{BOT_NAME_PREFIX} 2"
        assert info[1].is_bot is True
        assert info[2].name == "Bob"
        assert info[2].is_bot is False
        assert info[2].is_owner is False
        assert info[2].ready is True
        assert info[3].name == f"{BOT_NAME_PREFIX} 4"
        assert info[3].is_bot is True

    def test_lobby_room_get_player_info__when_owner_not_ready__should_show_owner_ready(self):
        room = LobbyRoom(room_id="r1")
        _seat(room, 0, "conn-1", ready=False)

        info = room.get_player_info()
        assert info[0].ready is True


class TestMemberOfUser:
    def test_lobby_room_member_of_user__should_match_only_seated_users(self):
        room = LobbyRoom(room_id="r1")
        member = _seat(room, 0, "conn-1")
        assert room.member_of_user("user-conn-1") is member
        assert room.member_of_user("user-other") is None
