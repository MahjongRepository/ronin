from game.messaging.types import SessionErrorCode
from game.tests.mocks import MockConnection

from .helpers import create_started_game, participant_of


class TestSeatBindingOnStart:
    async def test_session_binding__when_game_starts__should_bind_seat_to_each_participant(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        assert [participant_of(manager, conn).seat for conn in conns] == [0, 1]


class TestSessionCleanup:
    async def test_session_binding__when_all_players_leave__should_release_the_game_and_its_tickets(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_ticket = participant_of(manager, conns[0]).ticket

        manager.disconnect(conns[0])
        manager.disconnect(conns[1])
        assert manager.get_game("game1") is None

        reconnecting = MockConnection()
        manager.register_connection(reconnecting)
        manager.reconnect(reconnecting, game_id="game1", session_token=alice_ticket)
        assert [m["code"] for m in reconnecting.sent_messages] == [SessionErrorCode.RECONNECT_NO_SESSION]
