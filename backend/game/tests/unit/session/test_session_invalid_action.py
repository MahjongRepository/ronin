import logging
from unittest.mock import MagicMock

from game.logic.enums import GameAction
from game.logic.events import BroadcastTarget, EventType, ServiceEvent
from game.logic.exceptions import InvalidGameActionError
from game.messaging.types import SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.mocks import MockResultEvent
from game.wire.events import EVENT_TYPE_INT

from .helpers import create_started_game, wait_for_background_tasks

DISCARD_ERROR = InvalidGameActionError(action="discard", seat=0, reason="tile not in hand")


class TestSessionManagerInvalidAction:
    async def test_invalid_action__when_player_sends_it__should_close_with_1008(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008
        assert conns[0]._close_reason == "invalid_game_action"

    async def test_invalid_action__when_player_sends_it__should_replace_player_with_ai(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, seat):
            replace_calls.append((game_id, seat))
            return original_replace(game_id, seat)

        manager._game_service.replace_with_ai_player = tracking_replace
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", 0)

    async def test_invalid_action__when_player_sends_it__should_broadcast_player_left(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        left_msgs = [m for m in conns[1].sent_messages if m.get("type") == SessionMessageType.PLAYER_LEFT]
        assert len(left_msgs) == 1
        assert left_msgs[0]["player_name"] == "Alice"

    async def test_invalid_action__when_last_human_sends_it__should_clean_up_game(self, manager):
        conns = await create_started_game(manager, player_names=["Alice"])
        assert manager.get_game("game1") is not None

        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)
        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        # game should be cleaned up
        assert manager.get_game("game1") is None

    async def test_invalid_action__when_player_sends_it__should_log_warning(self, manager, caplog):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        with caplog.at_level(logging.WARNING):
            await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 1
        msg = warning_records[0].msg
        assert msg["event"] == "invalid game action"
        assert msg["action"] == "discard"
        assert msg["reason"] == "tile not in hand"

    async def test_invalid_action__when_player_replaced__should_broadcast_ai_pending_actions(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])

        ai_player_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                seat=0,
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target=BroadcastTarget(),
        )
        manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            return_value=[ai_player_event],
        )
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        # Bob should receive the AI player action event
        ai_player_msgs = [m for m in conns[1].sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(ai_player_msgs) == 1

    async def test_invalid_action__when_ai_replacement_raises__should_fail_the_game(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)
        manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            side_effect=ValueError("engine state broke during replacement"),
        )

        await router.handle_message(
            conns[0], {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": 0}
        )
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert [(c._close_code, c._close_reason) for c in conns] == [(1011, "internal_error")] * 2

    async def test_invalid_action__when_offender_leaves_afterwards__should_not_replace_again(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)
        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})

        # player.game_id is now None, so leave_game should return early
        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, seat):
            replace_calls.append((game_id, seat))
            return original_replace(game_id, seat)

        manager._game_service.replace_with_ai_player = tracking_replace

        # simulate the WebSocket disconnect handler calling leave_game
        await manager.leave_game(conns[0])
        # no additional replacement should have happened
        assert len(replace_calls) == 0
