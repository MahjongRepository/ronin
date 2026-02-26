"""Tests for LobbyRoom model — seat array behavior and derived properties."""

from lobby.rooms.models import BOT_NAME_PREFIX, TOTAL_SEATS, LobbyPlayer, LobbyRoom


class TestSeatArray:
    def test_new_room_has_four_none_seats(self):
        room = LobbyRoom(room_id="r1")
        assert room.seats == [None, None, None, None]
        assert len(room.seats) == TOTAL_SEATS

    def test_first_open_seat_on_empty_room(self):
        room = LobbyRoom(room_id="r1")
        assert room.first_open_seat() == 0

    def test_first_open_seat_skips_occupied(self):
        room = LobbyRoom(room_id="r1")
        room.seats[0] = "conn-1"
        assert room.first_open_seat() == 1

    def test_first_open_seat_returns_none_when_full(self):
        room = LobbyRoom(room_id="r1")
        room.seats = ["c0", "c1", "c2", "c3"]
        assert room.first_open_seat() is None

    def test_first_open_seat_finds_gap_in_middle(self):
        room = LobbyRoom(room_id="r1")
        room.seats = ["c0", None, "c2", "c3"]
        assert room.first_open_seat() == 1

    def test_seat_of_returns_correct_index(self):
        room = LobbyRoom(room_id="r1")
        room.seats[2] = "conn-x"
        assert room.seat_of("conn-x") == 2

    def test_seat_of_returns_none_for_unknown(self):
        room = LobbyRoom(room_id="r1")
        assert room.seat_of("conn-unknown") is None

    def test_seat_stability_across_leave_rejoin(self):
        """Leaving seat 1 restores it to bot. A new joiner takes seat 1 (first open), not seat 3."""
        room = LobbyRoom(room_id="r1")
        room.seats = ["conn-0", "conn-1", "conn-2", "conn-3"]

        # Simulate conn-1 leaving seat 1
        room.seats[1] = None

        # Next join should take seat 1, not seat 3
        assert room.first_open_seat() == 1

    def test_seat_stability_leave_does_not_shift_others(self):
        """Leaving seat 1 doesn't move seat 2 or 3."""
        room = LobbyRoom(room_id="r1")
        room.seats = ["conn-0", "conn-1", "conn-2", None]

        room.seats[1] = None

        assert room.seats == ["conn-0", None, "conn-2", None]
        assert room.seat_of("conn-0") == 0
        assert room.seat_of("conn-2") == 2


class TestDerivedProperties:
    def test_num_ai_players_empty_room(self):
        room = LobbyRoom(room_id="r1")
        assert room.num_ai_players == 4

    def test_num_ai_players_with_humans(self):
        room = LobbyRoom(room_id="r1")
        room.seats[0] = "conn-1"
        assert room.num_ai_players == 3

    def test_num_ai_players_full_room(self):
        room = LobbyRoom(room_id="r1")
        room.seats = ["c0", "c1", "c2", "c3"]
        assert room.num_ai_players == 0

    def test_is_full_when_all_seats_occupied(self):
        room = LobbyRoom(room_id="r1")
        room.seats = ["c0", "c1", "c2", "c3"]
        assert room.is_full is True

    def test_is_full_when_seats_available(self):
        room = LobbyRoom(room_id="r1")
        room.seats[0] = "c0"
        assert room.is_full is False

    def test_is_empty_with_no_players(self):
        room = LobbyRoom(room_id="r1")
        assert room.is_empty is True

    def test_is_empty_with_players(self):
        room = LobbyRoom(room_id="r1")
        room.players["c1"] = LobbyPlayer(connection_id="c1", user_id="u1", username="Alice")
        assert room.is_empty is False


class TestCanStart:
    def test_empty_room_cannot_start(self):
        room = LobbyRoom(room_id="r1")
        assert room.can_start is False

    def test_owner_alone_can_start(self):
        """Owner playing with 3 bots — can start immediately."""
        room = LobbyRoom(room_id="r1")
        room.host_connection_id = "conn-1"
        room.seats[0] = "conn-1"
        room.players["conn-1"] = LobbyPlayer(
            connection_id="conn-1",
            user_id="u1",
            username="Owner",
        )
        assert room.can_start is True

    def test_cannot_start_when_non_owner_not_ready(self):
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

    def test_can_start_when_all_non_owners_ready(self):
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

    def test_can_start_requires_all_non_owners_ready(self):
        """With 3 humans, all non-owners must be ready."""
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
    def test_empty_room_returns_four_bots(self):
        room = LobbyRoom(room_id="r1")
        info = room.get_player_info()
        assert len(info) == 4
        for i, p in enumerate(info):
            assert p.is_bot is True
            assert p.ready is True
            assert p.is_owner is False
            assert p.name == f"{BOT_NAME_PREFIX} {i + 1}"

    def test_mixed_room_preserves_seat_order(self):
        """Seat 0 = human owner, seat 1 = bot, seat 2 = human, seat 3 = bot."""
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

    def test_owner_shown_as_ready_even_when_not(self):
        """Owner's ready state is always True in player info."""
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

    def test_bot_names_tied_to_seat_index(self):
        """Bot names use seat index, not count. Seat 2 bot is always 'Tsumogiri Bot 3'."""
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
    def test_has_user_when_present(self):
        room = LobbyRoom(room_id="r1")
        room.players["conn-1"] = LobbyPlayer(
            connection_id="conn-1",
            user_id="u1",
            username="Alice",
        )
        assert room.has_user("u1") is True

    def test_has_user_when_absent(self):
        room = LobbyRoom(room_id="r1")
        assert room.has_user("u1") is False
