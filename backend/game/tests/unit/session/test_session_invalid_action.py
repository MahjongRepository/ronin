import logging
from unittest.mock import MagicMock

from game.logic.enums import GameAction, GameErrorCode, TimeoutType, WaitKind
from game.logic.events import BroadcastTarget, EventType, ServiceEvent
from game.logic.exceptions import InvalidGameActionError
from game.messaging.types import SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.session.manager import SessionManager
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.mocks import FakeGameRepository, MockResultEvent, mock_update
from game.wire.events import EVENT_TYPE_INT

from .helpers import (
    arrange_pon_now_and_on_the_next_draw,
    create_started_game,
    current_wait_id,
    fire_turn_timer_now,
    run_timeout,
    wait_for_background_tasks,
)

DISCARD_ERROR = InvalidGameActionError(action="discard", seat=0, reason="tile not in hand")


class TestSessionManagerInvalidAction:
    async def test_invalid_action__when_player_sends_it__should_close_with_1008(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
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

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", 0)

    async def test_invalid_action__when_player_sends_it__should_broadcast_player_left(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
        left_msgs = [m for m in conns[1].sent_messages if m.get("type") == SessionMessageType.PLAYER_LEFT]
        assert len(left_msgs) == 1
        assert left_msgs[0]["player_name"] == "Alice"

    async def test_invalid_action__when_last_human_sends_it__should_clean_up_game(self, manager):
        conns = await create_started_game(manager, player_names=["Alice"])
        assert manager.get_game("game1") is not None

        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)
        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
        # game should be cleaned up
        assert manager.get_game("game1") is None

    async def test_invalid_action__when_player_sends_it__should_log_warning(self, manager, caplog):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        with caplog.at_level(logging.WARNING):
            await manager.handle_game_action(
                conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager)
            )

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 1
        msg = warning_records[0].msg
        assert msg["event"] == "invalid game action"
        assert msg["action"] == "discard"
        assert msg["reason"] == "tile not in hand"

    async def test_invalid_action__when_player_replaced__should_broadcast_ai_pending_actions(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])

        ai_player_event = ServiceEvent(
            data=MockResultEvent(
                type=EventType.DRAW,
                target=BroadcastTarget(),
                seat=0,
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
        )
        manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            return_value=mock_update([ai_player_event]),
        )
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
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
            conns[0],
            {
                "t": WireClientMessageType.GAME_ACTION,
                "wi": current_wait_id(manager),
                "a": WireGameAction.DISCARD,
                "ti": 0,
            },
        )
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert [(c._close_code, c._close_reason) for c in conns] == [(1011, "internal_error")] * 2

    async def test_invalid_action__when_offender_leaves_afterwards__should_not_replace_again(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)
        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))

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


class TestStaleAction:
    async def test_stale_action__when_a_discard_raced_its_own_turn_timeout__should_be_refused_with_nothing_changed(
        self, seeded_engine
    ):
        manager = SessionManager(seeded_engine, game_repository=FakeGameRepository())
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        conns = await create_started_game(manager, player_names=["Alice"])
        alice = conns[0]
        alice_seat = manager._players[alice.connection_id].seat
        timed_out_wait = current_wait_id(manager)
        timed_out_draw = seeded_engine.get_game_state("game1").round_state.players[alice_seat].tiles[-1]
        await fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        state_before = seeded_engine.get_game_state("game1")
        awaiting_before = manager.get_game("game1").awaiting
        deadline = manager._timer_manager.get_timer("game1", alice_seat).task
        alice._outbox.clear()

        await router.handle_message(
            alice,
            {
                "t": WireClientMessageType.GAME_ACTION,
                "wi": timed_out_wait,
                "a": WireGameAction.DISCARD,
                "ti": timed_out_draw,
            },
        )
        assert [(m["t"], m["cd"]) for m in alice.sent_messages] == [
            (EVENT_TYPE_INT[EventType.ERROR], GameErrorCode.STALE_ACTION)
        ]
        assert not alice.is_closed
        assert seeded_engine.get_game_state("game1") is state_before
        assert manager.get_game("game1").awaiting is awaiting_before
        assert manager._timer_manager.get_timer("game1", alice_seat).task is deadline

        await manager.shutdown()

    async def test_stale_action__when_a_pass_arrives_after_a_newer_prompt_opened__should_leave_that_prompt_pending(
        self, seeded_engine
    ):
        manager = SessionManager(seeded_engine, game_repository=FakeGameRepository())
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice, bob = (manager._players[conn.connection_id].seat for conn in conns)
        discarded_four_pin = arrange_pon_now_and_on_the_next_draw(seeded_engine, discarder=alice, caller=bob)
        await manager.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={"tile_id": discarded_four_pin}, wait_id=current_wait_id(manager)
        )
        first_prompt = manager.get_game("game1").awaiting
        assert (first_prompt.kind, first_prompt.seats) == (WaitKind.CALL, frozenset({bob}))

        await run_timeout(manager, game_id="game1", timeout_type=TimeoutType.MELD, seat=bob)
        newer_prompt = manager.get_game("game1").awaiting
        assert (newer_prompt.kind, newer_prompt.seats) == (WaitKind.CALL, frozenset({bob}))
        assert newer_prompt.wait_id != first_prompt.wait_id
        state_before = seeded_engine.get_game_state("game1")
        conns[1]._outbox.clear()

        await manager.handle_game_action(conns[1], action=GameAction.PASS, data={}, wait_id=first_prompt.wait_id)
        assert [m["cd"] for m in conns[1].sent_messages] == [GameErrorCode.STALE_ACTION]
        assert seeded_engine.get_game_state("game1") is state_before
        assert bob in state_before.round_state.pending_call_prompt.pending_seats

        await manager.shutdown()
