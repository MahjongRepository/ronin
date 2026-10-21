from lobby.rooms.models import BOT_NAME_PREFIX, TOTAL_SEATS, LobbyPlayer, LobbyRoom


class TestSeatArray:
    def test_lobby_room_seats__when_new_room__should_have_four_empty_seats(self):
        room = LobbyRoom(room_id="r1")
        assert room.seats == [None, None, None, None]
        assert len(room.seats) == TOTAL_SEATS

    def test_lobby_room_first_open_seat__when_room_empty__should_return_zero(self):
        room = LobbyRoom(room_id="r1")
        assert room.first_open_seat() == 0

    def test_lobby_room_first_open_seat__when_seat_zero_taken__should_return_one(self):
        room = LobbyRoom(room_id="r1")
        room.seats[0] = "conn-1"
        assert room.first_open_seat() == 1

    def test_lobby_room_first_open_seat__when_room_full__should_return_none(self):
        room = LobbyRoom(room_id="r1")
        room.seats = ["c0", "c1", "c2", "c3"]
        assert room.first_open_seat() is None

    def test_lobby_room_first_open_seat__when_gap_in_middle__should_return_gap(self):
        room = LobbyRoom(room_id="r1")
        room.seats = ["c0", None, "c2", "c3"]
        assert room.first_open_seat() == 1

    def test_lobby_room_seat_of__should_return_seat_index(self):
        room = LobbyRoom(room_id="r1")
        room.seats[2] = "conn-x"
        assert room.seat_of("conn-x") == 2

    def test_lobby_room_seat_of__when_connection_unknown__should_return_none(self):
        room = LobbyRoom(room_id="r1")
        assert room.seat_of("conn-unknown") is None

    def test_lobby_room_seats__when_seat_freed__should_reuse_it_for_next_join(self):
        room = LobbyRoom(room_id="r1")
        room.seats = ["conn-0", "conn-1", "conn-2", "conn-3"]
        # Simulate conn-1 leaving seat 1
        room.seats[1] = None

        # Next join should take seat 1, not seat 3
        assert room.first_open_seat() == 1

    def test_lobby_room_seats__when_seat_freed__should_not_shift_other_players(self):
        room = LobbyRoom(room_id="r1")
        room.seats = ["conn-0", "conn-1", "conn-2", None]

        room.seats[1] = None
        assert room.seats == ["conn-0", None, "conn-2", None]
        assert room.seat_of("conn-0") == 0
        assert room.seat_of("conn-2") == 2


class TestDerivedProperties:
    def test_lobby_room_num_ai_players__when_room_empty__should_be_four(self):
        room = LobbyRoom(room_id="r1")
        assert room.num_ai_players == 4

    def test_lobby_room_num_ai_players__when_one_human__should_be_three(self):
        room = LobbyRoom(room_id="r1")
        room.seats[0] = "conn-1"
        assert room.num_ai_players == 3

    def test_lobby_room_num_ai_players__when_room_full__should_be_zero(self):
        room = LobbyRoom(room_id="r1")
        room.seats = ["c0", "c1", "c2", "c3"]
        assert room.num_ai_players == 0

    def test_lobby_room_is_full__when_all_seats_occupied__should_be_true(self):
        room = LobbyRoom(room_id="r1")
        room.seats = ["c0", "c1", "c2", "c3"]
        assert room.is_full is True

    def test_lobby_room_is_full__when_seat_available__should_be_false(self):
        room = LobbyRoom(room_id="r1")
        room.seats[0] = "c0"
        assert room.is_full is False

    def test_lobby_room_is_empty__when_no_players__should_be_true(self):
        room = LobbyRoom(room_id="r1")
        assert room.is_empty is True

    def test_lobby_room_is_empty__when_player_present__should_be_false(self):
        room = LobbyRoom(room_id="r1")
        room.players["c1"] = LobbyPlayer(connection_id="c1", user_id="u1", username="Alice")
        assert room.is_empty is False


class TestCanStart:
    def test_lobby_room_can_start__when_room_empty__should_be_false(self):
        room = LobbyRoom(room_id="r1")
        assert room.can_start is False

    def test_lobby_room_can_start__when_owner_alone__should_be_true(self):
        room = LobbyRoom(room_id="r1")
        room.host_connection_id = "conn-1"
        room.seats[0] = "conn-1"
        room.players["conn-1"] = LobbyPlayer(
            connection_id="conn-1",
            user_id="u1",
            username="Owner",
        )

        assert room.can_start is True

    def test_lobby_room_can_start__when_non_owner_not_ready__should_be_false(self):
        room = LobbyRoom(room_id="r1")
        room.host_connection_id = "conn-1"
        room.seats[0] = "conn-1"
        room.seats[1] = "conn-2"
        room.players["conn-1"] = LobbyPlayer(
            connection_id="conn-1",
            user_id="u1",
            username="Owner",
        )
        room.players["conn-2"] = LobbyPlayer(
            connection_id="conn-2",
            user_id="u2",
            username="Bob",
            ready=False,
        )

        assert room.can_start is False

    def test_lobby_room_can_start__when_all_non_owners_ready__should_be_true(self):
        room = LobbyRoom(room_id="r1")
        room.host_connection_id = "conn-1"
        room.seats[0] = "conn-1"
        room.seats[1] = "conn-2"
        room.players["conn-1"] = LobbyPlayer(
            connection_id="conn-1",
            user_id="u1",
            username="Owner",
        )
        room.players["conn-2"] = LobbyPlayer(
            connection_id="conn-2",
            user_id="u2",
            username="Bob",
            ready=True,
        )

        assert room.can_start is True

    def test_lobby_room_can_start__when_one_of_several_non_owners_not_ready__should_be_false(self):
        room = LobbyRoom(room_id="r1")
        room.host_connection_id = "conn-1"
        for i, cid in enumerate(["conn-1", "conn-2", "conn-3"]):
            room.seats[i] = cid
            room.players[cid] = LobbyPlayer(
                connection_id=cid,
                user_id=f"u{i}",
                username=f"P{i}",
            )

        room.players["conn-2"].ready = True
        room.players["conn-3"].ready = False
        assert room.can_start is False

        room.players["conn-3"].ready = True
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
        room.host_connection_id = "conn-1"
        room.seats[0] = "conn-1"
        room.seats[2] = "conn-2"
        room.players["conn-1"] = LobbyPlayer(
            connection_id="conn-1",
            user_id="u1",
            username="Alice",
        )
        room.players["conn-2"] = LobbyPlayer(
            connection_id="conn-2",
            user_id="u2",
            username="Bob",
            ready=True,
        )

        info = room.get_player_info()
        assert len(info) == 4
        # Seat 0: owner (Alice), always shown as ready
        assert info[0].name == "Alice"
        assert info[0].is_bot is False
        assert info[0].is_owner is True
        assert info[0].ready is True
        # Seat 1: bot
        assert info[1].name == f"{BOT_NAME_PREFIX} 2"
        assert info[1].is_bot is True
        # Seat 2: human (Bob), ready
        assert info[2].name == "Bob"
        assert info[2].is_bot is False
        assert info[2].is_owner is False
        assert info[2].ready is True
        # Seat 3: bot
        assert info[3].name == f"{BOT_NAME_PREFIX} 4"
        assert info[3].is_bot is True

    def test_lobby_room_get_player_info__when_owner_not_ready__should_show_owner_ready(self):
        room = LobbyRoom(room_id="r1")
        room.host_connection_id = "conn-1"
        room.seats[0] = "conn-1"
        room.players["conn-1"] = LobbyPlayer(
            connection_id="conn-1",
            user_id="u1",
            username="Owner",
            ready=False,
        )

        info = room.get_player_info()
        assert info[0].ready is True

    def test_lobby_room_get_player_info__should_name_bots_by_seat_index(self):
        room = LobbyRoom(room_id="r1")
        room.seats[0] = "conn-1"
        room.players["conn-1"] = LobbyPlayer(
            connection_id="conn-1",
            user_id="u1",
            username="Alice",
        )

        info = room.get_player_info()
        # Seats 1, 2, 3 are bots
        assert info[1].name == f"{BOT_NAME_PREFIX} 2"
        assert info[2].name == f"{BOT_NAME_PREFIX} 3"
        assert info[3].name == f"{BOT_NAME_PREFIX} 4"


class TestHasUser:
    def test_lobby_room_has_user__when_user_present__should_be_true(self):
        room = LobbyRoom(room_id="r1")
        room.players["conn-1"] = LobbyPlayer(
            connection_id="conn-1",
            user_id="u1",
            username="Alice",
        )
        assert room.has_user("u1") is True

    def test_lobby_room_has_user__when_user_absent__should_be_false(self):
        room = LobbyRoom(room_id="r1")
        assert room.has_user("u1") is False
