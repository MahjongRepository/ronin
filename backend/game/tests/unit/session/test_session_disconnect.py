from unittest.mock import MagicMock

from game.logic.enums import GameAction
from game.logic.events import BroadcastTarget, EventType
from game.session.models import GameLifecycle
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import MockResultEvent, mock_update
from game.wire.events import EVENT_TYPE_INT

from .helpers import create_started_game, game_of, participant_of, runtime_of


class TestSessionManagerDisconnect:
    async def test_disconnect__when_one_of_two_humans_leaves__should_replace_with_ai_and_keep_game(self, seeded_engine):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat, bob_seat = (participant_of(manager, conn).seat for conn in conns)

        manager.disconnect(conns[0])
        assert manager.get_game("game1") is not None
        snapshot = seeded_engine.build_reconnection_snapshot(runtime_of(manager), bob_seat)
        assert snapshot.players[alice_seat].is_ai_player is True
        assert snapshot.players[bob_seat].is_ai_player is False

    async def test_disconnect__when_last_human_leaves__should_not_replace_with_ai_and_clean_up_game(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        assert game_of(manager).lifecycle is GameLifecycle.PLAYING

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, seat):
            replace_calls.append((game_id, seat))
            return original_replace(game_id, seat)

        manager._game_service.replace_with_ai_player = tracking_replace

        # first player leaves (triggers AI player replacement)
        manager.disconnect(conns[0])
        assert len(replace_calls) == 1

        # second player leaves (last player -- no AI player replacement, game cleaned up)
        manager.disconnect(conns[1])
        assert len(replace_calls) == 1  # no additional call
        assert manager.get_game("game1") is None

    async def test_disconnect__when_ai_replacement_produces_events__should_broadcast_them(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])

        # make process_ai_player_actions_after_replacement return an event
        ai_player_event = MockResultEvent(
            type=EventType.DRAW,
            target=BroadcastTarget(),
            seat=0,
            action=GameAction.DISCARD,
            input={},
            success=True,
        )
        manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            return_value=mock_update([ai_player_event]),
        )

        manager.disconnect(conns[0])
        # Bob should receive the AI player action event
        ai_player_msgs = [m for m in conns[1].sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(ai_player_msgs) == 1
