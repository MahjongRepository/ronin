import logging
from unittest.mock import MagicMock

from game.logic.enums import GameAction, GameErrorCode, TimeoutType, WaitKind
from game.logic.events import BroadcastTarget, EventType, ServiceEvent
from game.logic.exceptions import InvalidGameActionError
from game.messaging.types import SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import MockResultEvent, mock_update
from game.wire.events import EVENT_TYPE_INT

from .helpers import (
    arrange_pon_now_and_on_the_next_draw,
    create_started_game,
    current_wait_id,
    fire_turn_timer_now,
    participant_of,
    run_timeout,
    runtime_of,
    wait_for_background_tasks,
)

_SEAT_CHANGE_TYPES = (SessionMessageType.PLAYER_LEFT, SessionMessageType.PLAYER_RECONNECTED)
DISCARD_ERROR = InvalidGameActionError(action="discard", seat=0, reason="tile not in hand")


class TestSessionManagerInvalidAction:
    async def test_invalid_action__when_player_sends_it__should_close_with_1008(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008
        assert conns[0]._close_reason == "invalid_game_action"

    async def test_invalid_action__when_player_sends_it__should_replace_player_with_ai(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(runtime, seat):
            replace_calls.append((runtime, seat))
            return original_replace(runtime, seat)

        manager._game_service.replace_with_ai_player = tracking_replace
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
        assert replace_calls == [(runtime_of(manager), 0)]

    async def test_invalid_action__when_player_sends_it__should_broadcast_player_left(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
        left_msgs = [m for m in conns[1].sent_messages if m.get("type") == SessionMessageType.PLAYER_LEFT]
        assert len(left_msgs) == 1
        assert left_msgs[0]["player_name"] == "Alice"

    async def test_invalid_action__when_last_human_sends_it__should_clean_up_game(self, manager):
        conns = create_started_game(manager, player_names=["Alice"])
        assert manager.get_game("game1") is not None

        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)
        manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
        # game should be cleaned up
        assert manager.get_game("game1") is None

    async def test_invalid_action__when_player_sends_it__should_log_warning(self, manager, caplog):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)

        with caplog.at_level(logging.WARNING):
            manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 1
        msg = warning_records[0].msg
        assert msg["event"] == "invalid game action"
        assert msg["action"] == "discard"
        assert msg["reason"] == "tile not in hand"

    async def test_invalid_action__when_player_replaced__should_broadcast_ai_pending_actions(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])

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

        manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
        # Bob should receive the AI player action event
        ai_player_msgs = [m for m in conns[1].sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(ai_player_msgs) == 1

    async def test_invalid_action__when_ai_replacement_raises__should_fail_the_game(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)
        manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            side_effect=ValueError("engine state broke during replacement"),
        )

        router.handle_message(
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
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.handle_action = MagicMock(side_effect=DISCARD_ERROR)
        manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, seat):
            replace_calls.append((game_id, seat))
            return original_replace(game_id, seat)

        manager._game_service.replace_with_ai_player = tracking_replace

        manager.disconnect(conns[0])
        # no additional replacement should have happened
        assert len(replace_calls) == 0


class TestKickedConnection:
    async def test_invalid_action__when_kicked_client_pipelines_a_reconnect__should_drop_it_and_keep_the_ai_seat(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        player_of = {conn: participant_of(manager, conn) for conn in conns}
        awaited_seat = next(iter(manager.get_game("game1").awaiting.seats))
        kicked = next(conn for conn in conns if player_of[conn].seat == awaited_seat)
        other = next(conn for conn in conns if player_of[conn].seat != awaited_seat)
        kicked_token = player_of[kicked].ticket
        held_tiles = set(runtime_of(manager).state.round_state.players[awaited_seat].tiles)
        foreign_tile = next(tile for tile in range(136) if tile not in held_tiles)

        manager.handle_game_action(
            kicked, action=GameAction.DISCARD, data={"tile_id": foreign_tile}, wait_id=current_wait_id(manager)
        )
        assert kicked._close_code == 1008

        manager.reconnect(kicked, game_id="game1", session_token=kicked_token)
        assert manager.get_connection_game(kicked) is None
        assert not player_of[kicked].is_connected
        other_seat = player_of[other].seat
        assert (
            seeded_engine.build_reconnection_snapshot(runtime_of(manager), other_seat)
            .players[awaited_seat]
            .is_ai_player
        )
        assert [m["type"] for m in other.sent_messages if m.get("type") in _SEAT_CHANGE_TYPES] == [
            SessionMessageType.PLAYER_LEFT
        ]

        await manager.shutdown()


class TestStaleAction:
    async def test_stale_action__when_a_discard_raced_its_own_turn_timeout__should_be_refused_with_nothing_changed(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        conns = create_started_game(manager, player_names=["Alice"])
        alice = conns[0]
        alice_seat = participant_of(manager, alice).seat
        timed_out_wait = current_wait_id(manager)
        timed_out_draw = runtime_of(manager).state.round_state.players[alice_seat].tiles[-1]
        await fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        state_before = runtime_of(manager).state
        awaiting_before = manager.get_game("game1").awaiting
        deadline = participant_of(manager, alice).timer.task
        alice._outbox.clear()

        router.handle_message(
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
        assert runtime_of(manager).state is state_before
        assert manager.get_game("game1").awaiting is awaiting_before
        assert participant_of(manager, alice).timer.task is deadline

        await manager.shutdown()

    async def test_stale_action__when_a_pass_arrives_after_a_newer_prompt_opened__should_leave_that_prompt_pending(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice, bob = (participant_of(manager, conn).seat for conn in conns)
        discarded_four_pin = arrange_pon_now_and_on_the_next_draw(runtime_of(manager), discarder=alice, caller=bob)
        manager.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={"tile_id": discarded_four_pin}, wait_id=current_wait_id(manager)
        )
        first_prompt = manager.get_game("game1").awaiting
        assert (first_prompt.kind, first_prompt.seats) == (WaitKind.CALL, frozenset({bob}))

        run_timeout(manager, game_id="game1", timeout_type=TimeoutType.MELD, seat=bob)
        newer_prompt = manager.get_game("game1").awaiting
        assert (newer_prompt.kind, newer_prompt.seats) == (WaitKind.CALL, frozenset({bob}))
        assert newer_prompt.wait_id != first_prompt.wait_id
        state_before = runtime_of(manager).state
        conns[1]._outbox.clear()

        manager.handle_game_action(conns[1], action=GameAction.PASS, data={}, wait_id=first_prompt.wait_id)
        assert [m["cd"] for m in conns[1].sent_messages] == [GameErrorCode.STALE_ACTION]
        assert runtime_of(manager).state is state_before
        assert bob in state_before.round_state.pending_call_prompt.pending_seats

        await manager.shutdown()
