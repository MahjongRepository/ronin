from game.engine import EventType, Turn
from game.session.models import GameLifecycle
from game.tests.helpers.session import make_session_manager
from game.wire.events import EVENT_TYPE_INT
from game.wire.keys import WireKey

from .helpers import ENGINE_SEED, create_started_game, game_of, participant_of


class TestSessionManagerDisconnect:
    async def test_disconnect__when_one_of_two_humans_leaves__should_replace_with_ai_and_keep_game(self, real_engine):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat, bob_seat = (participant_of(manager, conn).seat for conn in conns)

        manager.disconnect(conns[0])
        assert manager.get_game("game1") is not None
        game = game_of(manager)
        assert (game.is_ai_seat(alice_seat), game.is_ai_seat(bob_seat)) == (True, False)
        assert manager.stats["ai_replacements"] == 1

    async def test_disconnect__when_last_human_leaves__should_not_replace_with_ai_and_clean_up_game(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        assert game_of(manager).lifecycle is GameLifecycle.PLAYING

        manager.disconnect(conns[0])
        assert manager.stats["ai_replacements"] == 1

        manager.disconnect(conns[1])
        assert manager.stats["ai_replacements"] == 1
        assert manager.get_game("game1") is None

    async def test_disconnect__when_the_seat_owed_its_turn__should_play_it_as_the_ai_player_for_the_others(
        self, manager
    ):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat, bob_seat = (participant_of(manager, conn).seat for conn in conns)
        assert game_of(manager).awaiting == Turn(seat=alice_seat)

        manager.disconnect(conns[0])
        ai_player_moves = [
            m for m in conns[1].sent_messages if m.get(WireKey.EVENT_TYPE) == EVENT_TYPE_INT[EventType.DRAW]
        ]
        assert len(ai_player_moves) == 1
        assert game_of(manager).awaiting == Turn(seat=bob_seat)
