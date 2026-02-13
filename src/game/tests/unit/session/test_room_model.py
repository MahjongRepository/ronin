import pytest

from game.session.models import MAX_BOTS
from game.session.room import Room, RoomPlayer, RoomPlayerInfo
from game.tests.mocks import MockConnection


class TestRoomCreation:
    """Tests for Room creation and validation."""

    def test_create_room_defaults(self):
        room = Room(room_id="room1")
        assert room.room_id == "room1"
        assert room.num_bots == 3
        assert room.host_connection_id is None
        assert room.transitioning is False
        assert room.players == {}

    def test_create_room_with_bots(self):
        room = Room(room_id="room1", num_bots=1)
        assert room.num_bots == 1
        assert room.humans_needed == 3

    def test_create_room_zero_bots(self):
        room = Room(room_id="room1", num_bots=0)
        assert room.num_bots == 0
        assert room.humans_needed == 4

    def test_create_room_max_bots(self):
        room = Room(room_id="room1", num_bots=MAX_BOTS)
        assert room.num_bots == MAX_BOTS
        assert room.humans_needed == 1

    def test_create_room_invalid_bots_negative(self):
        with pytest.raises(ValueError, match="num_bots must be 0-3"):
            Room(room_id="room1", num_bots=-1)

    def test_create_room_invalid_bots_too_many(self):
        with pytest.raises(ValueError, match="num_bots must be 0-3"):
            Room(room_id="room1", num_bots=4)


class TestRoomProperties:
    """Tests for Room computed properties."""

    def test_humans_needed(self):
        assert Room(room_id="r", num_bots=3).humans_needed == 1
        assert Room(room_id="r", num_bots=2).humans_needed == 2
        assert Room(room_id="r", num_bots=1).humans_needed == 3
        assert Room(room_id="r", num_bots=0).humans_needed == 4

    def test_total_seats(self):
        room = Room(room_id="r")
        assert room.total_seats == 4

    def test_is_empty_when_no_players(self):
        room = Room(room_id="r")
        assert room.is_empty

    def test_is_empty_when_has_players(self):
        room = Room(room_id="r")
        conn = MockConnection()
        rp = RoomPlayer(connection=conn, name="Alice", room_id="r", session_token="tok")
        room.players[conn.connection_id] = rp
        assert not room.is_empty

    def test_player_count(self):
        room = Room(room_id="r")
        assert room.player_count == 0
        conn = MockConnection()
        rp = RoomPlayer(connection=conn, name="Alice", room_id="r", session_token="tok")
        room.players[conn.connection_id] = rp
        assert room.player_count == 1

    def test_player_names(self):
        room = Room(room_id="r")
        conn1 = MockConnection()
        conn2 = MockConnection()
        rp1 = RoomPlayer(connection=conn1, name="Alice", room_id="r", session_token="tok-a")
        rp2 = RoomPlayer(connection=conn2, name="Bob", room_id="r", session_token="tok-b")
        room.players[conn1.connection_id] = rp1
        room.players[conn2.connection_id] = rp2
        assert set(room.player_names) == {"Alice", "Bob"}


class TestRoomFullness:
    """Tests for room is_full check."""

    def test_not_full_when_empty(self):
        room = Room(room_id="r", num_bots=2)
        assert not room.is_full

    def test_full_when_at_capacity(self):
        room = Room(room_id="r", num_bots=2)  # needs 2 humans
        for i in range(2):
            conn = MockConnection()
            rp = RoomPlayer(connection=conn, name=f"Player{i}", room_id="r", session_token=f"tok-{i}")
            room.players[conn.connection_id] = rp
        assert room.is_full

    def test_not_full_when_under_capacity(self):
        room = Room(room_id="r", num_bots=2)  # needs 2 humans
        conn = MockConnection()
        rp = RoomPlayer(connection=conn, name="Alice", room_id="r", session_token="tok")
        room.players[conn.connection_id] = rp
        assert not room.is_full


class TestRoomReady:
    """Tests for room all_ready check."""

    def test_all_ready_empty_room_not_ready(self):
        room = Room(room_id="r", num_bots=3)  # needs 1 human
        assert not room.all_ready

    def test_all_ready_single_player_not_ready(self):
        room = Room(room_id="r", num_bots=3)
        conn = MockConnection()
        rp = RoomPlayer(connection=conn, name="Alice", room_id="r", session_token="tok", ready=False)
        room.players[conn.connection_id] = rp
        assert not room.all_ready

    def test_all_ready_single_player_ready(self):
        room = Room(room_id="r", num_bots=3)
        conn = MockConnection()
        rp = RoomPlayer(connection=conn, name="Alice", room_id="r", session_token="tok", ready=True)
        room.players[conn.connection_id] = rp
        assert room.all_ready

    def test_all_ready_mixed_readiness(self):
        room = Room(room_id="r", num_bots=2)  # needs 2 humans
        conn1 = MockConnection()
        conn2 = MockConnection()
        rp1 = RoomPlayer(connection=conn1, name="Alice", room_id="r", session_token="tok-a", ready=True)
        rp2 = RoomPlayer(connection=conn2, name="Bob", room_id="r", session_token="tok-b", ready=False)
        room.players[conn1.connection_id] = rp1
        room.players[conn2.connection_id] = rp2
        assert not room.all_ready

    def test_all_ready_all_players_ready(self):
        room = Room(room_id="r", num_bots=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        rp1 = RoomPlayer(connection=conn1, name="Alice", room_id="r", session_token="tok-a", ready=True)
        rp2 = RoomPlayer(connection=conn2, name="Bob", room_id="r", session_token="tok-b", ready=True)
        room.players[conn1.connection_id] = rp1
        room.players[conn2.connection_id] = rp2
        assert room.all_ready

    def test_all_ready_not_enough_players(self):
        """Even if all present are ready, not enough to fill room."""
        room = Room(room_id="r", num_bots=2)  # needs 2 humans
        conn = MockConnection()
        rp = RoomPlayer(connection=conn, name="Alice", room_id="r", session_token="tok", ready=True)
        room.players[conn.connection_id] = rp
        assert not room.all_ready


class TestRoomGetPlayerInfo:
    """Tests for get_player_info."""

    def test_get_player_info_empty(self):
        room = Room(room_id="r")
        assert room.get_player_info() == []

    def test_get_player_info_with_players(self):
        room = Room(room_id="r")
        conn1 = MockConnection()
        conn2 = MockConnection()
        rp1 = RoomPlayer(connection=conn1, name="Alice", room_id="r", session_token="tok-a", ready=True)
        rp2 = RoomPlayer(connection=conn2, name="Bob", room_id="r", session_token="tok-b", ready=False)
        room.players[conn1.connection_id] = rp1
        room.players[conn2.connection_id] = rp2

        infos = room.get_player_info()
        assert len(infos) == 2
        assert all(isinstance(i, RoomPlayerInfo) for i in infos)
        names = {i.name for i in infos}
        assert names == {"Alice", "Bob"}


class TestRoomPlayer:
    """Tests for RoomPlayer dataclass."""

    def test_room_player_defaults(self):
        conn = MockConnection()
        rp = RoomPlayer(connection=conn, name="Alice", room_id="room1", session_token="tok")
        assert rp.name == "Alice"
        assert rp.room_id == "room1"
        assert rp.ready is False
        assert rp.connection_id == conn.connection_id

    def test_room_player_ready(self):
        conn = MockConnection()
        rp = RoomPlayer(connection=conn, name="Alice", room_id="room1", session_token="tok", ready=True)
        assert rp.ready is True
