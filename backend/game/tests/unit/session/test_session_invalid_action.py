import logging
from unittest.mock import MagicMock

import pytest

from game.engine import (
    Action,
    Call,
    Discard,
    EventType,
    Kan,
    KanType,
    Pass,
    Pon,
    Refusal,
    RefusalCode,
    RefusalKind,
    Riichi,
)
from game.messaging.game_errors import GameErrorCode
from game.messaging.types import SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.session import manager as manager_module
from game.session.timer import TimeoutType
from game.tests.helpers.auth import TEST_TICKET_SECRET
from game.tests.helpers.session import make_session_manager
from game.wire.events import EVENT_TYPE_INT
from game.wire.keys import WireKey

from .helpers import (
    ENGINE_SEED,
    arrange_pon_now_and_on_the_next_draw,
    create_started_game,
    current_wait_id,
    fire_turn_timer_now,
    game_of,
    participant_of,
    run_timeout,
    runtime_of,
    wait_for_background_tasks,
)

TILE_NOT_HELD = Refusal(kind=RefusalKind.NOT_OFFERED, code=RefusalCode.TILE_NOT_HELD)


class TestSessionManagerInvalidAction:
    async def test_invalid_action__when_player_sends_it__should_close_with_1008(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.script_act(TILE_NOT_HELD)

        manager.handle_game_action(
            conns[0], action=Discard(tile=0), called_tile=None, wait_id=current_wait_id(manager, conns[0])
        )
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008
        assert conns[0]._close_reason == "invalid_game_action"

    async def test_invalid_action__when_player_sends_it__should_seat_an_ai_player_that_plays_the_owed_turn(
        self, manager
    ):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.script_act(TILE_NOT_HELD)

        manager.handle_game_action(
            conns[0], action=Discard(tile=0), called_tile=None, wait_id=current_wait_id(manager, conns[0])
        )
        assert (game_of(manager).is_ai_seat(0), manager.stats["ai_replacements"]) == (True, 1)
        ai_player_msgs = [
            m for m in conns[1].sent_messages if m.get(WireKey.EVENT_TYPE) == EVENT_TYPE_INT[EventType.DRAW]
        ]
        assert len(ai_player_msgs) == 1

    async def test_invalid_action__when_last_human_sends_it__should_clean_up_game(self, manager):
        conns = create_started_game(manager, player_names=["Alice"])
        assert manager.get_game("game1") is not None

        manager._game_service.script_act(TILE_NOT_HELD)
        manager.handle_game_action(
            conns[0], action=Discard(tile=0), called_tile=None, wait_id=current_wait_id(manager, conns[0])
        )
        assert manager.get_game("game1") is None

    async def test_invalid_action__when_player_sends_it__should_log_warning(self, manager, caplog):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.script_act(TILE_NOT_HELD)

        with caplog.at_level(logging.WARNING):
            manager.handle_game_action(
                conns[0], action=Discard(tile=0), called_tile=None, wait_id=current_wait_id(manager, conns[0])
            )

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 1
        msg = warning_records[0].msg
        assert msg["event"] == "invalid game action"
        assert msg["action"] == "Discard(tile=0)"
        assert msg["reason"] == "tile_not_held"

    async def test_invalid_action__when_its_ai_player_raises__should_fail_the_game(self, manager, monkeypatch):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        manager._game_service.script_act(TILE_NOT_HELD)
        monkeypatch.setattr(manager_module, "choose_ai_action", MagicMock(side_effect=ValueError("engine state broke")))

        router.handle_message(
            conns[0],
            {
                WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
                WireKey.WAIT_ID: current_wait_id(manager, conns[0]),
                WireKey.ACTION: WireGameAction.DISCARD,
                WireKey.TILE_ID: 0,
            },
        )
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert [(c._close_code, c._close_reason) for c in conns] == [(1011, "internal_error")] * 2

    async def test_invalid_action__when_offender_leaves_afterwards__should_not_replace_again(self, manager):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        manager._game_service.script_act(TILE_NOT_HELD)
        manager.handle_game_action(
            conns[0], action=Discard(tile=0), called_tile=None, wait_id=current_wait_id(manager, conns[0])
        )

        manager.disconnect(conns[0])
        assert manager.stats["ai_replacements"] == 1


class TestKickedConnection:
    async def test_invalid_action__when_kicked_client_pipelines_a_reconnect__should_drop_it_and_keep_the_ai_seat(
        self, real_engine
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        player_of = {conn: participant_of(manager, conn) for conn in conns}
        awaited_seat = next(iter(manager.get_game("game1").awaiting.seats))
        kicked = next(conn for conn in conns if player_of[conn].seat == awaited_seat)
        other = next(conn for conn in conns if player_of[conn].seat != awaited_seat)
        kicked_token = player_of[kicked].ticket
        held_tiles = set(runtime_of(manager).state.round_state.players[awaited_seat].tiles)
        foreign_tile = next(tile for tile in range(136) if tile not in held_tiles)

        manager.handle_game_action(
            kicked, action=Discard(tile=foreign_tile), called_tile=None, wait_id=current_wait_id(manager, kicked)
        )
        assert kicked._close_code == 1008

        manager.reconnect(kicked, session_token=kicked_token)
        assert manager.get_connection_game(kicked) is None
        assert not player_of[kicked].is_connected
        assert game_of(manager).is_ai_seat(awaited_seat)
        assert [m for m in other.sent_messages if m.get(WireKey.SESSION_TYPE) == SessionMessageType.SEAT_CONTROL] == [
            {WireKey.SESSION_TYPE: "seat_control", WireKey.SEAT: awaited_seat, WireKey.SEAT_CONTROL_REASON: 0}
        ]

        await manager.shutdown()


class TestRuleRefusal:
    @pytest.mark.parametrize(
        ("action", "refusal_code", "error_code", "error_message"),
        [
            (
                Discard(tile=12),
                RefusalCode.KUIKAE,
                GameErrorCode.INVALID_DISCARD,
                "tile 12 is not a legal discard (kuikae or riichi tsumogiri)",
            ),
            (
                Riichi(tile=12),
                RefusalCode.RIICHI_BREAKS_TENPAI,
                GameErrorCode.INVALID_RIICHI,
                "hand is not tenpai after discarding tile 12",
            ),
        ],
        ids=["kuikae_discard", "riichi_breaking_tenpai"],
    )
    async def test_rule_refusal__when_the_engine_refuses_by_rule__should_answer_the_seat_and_keep_its_decision_open(
        self, manager, action: Action, refusal_code: RefusalCode, error_code: GameErrorCode, error_message: str
    ):
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        refused_wait = current_wait_id(manager, conns[0])
        deadline = participant_of(manager, conns[0]).timer.task
        conns[0]._outbox.clear()
        manager._game_service.act = MagicMock(return_value=Refusal(kind=RefusalKind.RULE, code=refusal_code))

        manager.handle_game_action(conns[0], action=action, called_tile=None, wait_id=refused_wait)
        assert [
            (m[WireKey.EVENT_TYPE], m[WireKey.GAME_ERROR_CODE], m[WireKey.GAME_ERROR_MESSAGE], m[WireKey.WAIT_ID])
            for m in conns[0].sent_messages
        ] == [(EVENT_TYPE_INT[EventType.ERROR], error_code, error_message, refused_wait)]
        assert not conns[0].is_closed
        assert current_wait_id(manager, conns[0]) == refused_wait
        assert participant_of(manager, conns[0]).timer.task is deadline

    async def test_rule_refusal__when_the_engine_refuses_an_action__should_name_the_wait_id_the_action_echoed(
        self, real_engine
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        conns = create_started_game(manager, player_names=["Alice"])
        refused_wait = current_wait_id(manager, conns[0])

        manager.handle_game_action(conns[0], action=Pass(), called_tile=None, wait_id=refused_wait)
        assert [
            (m[WireKey.EVENT_TYPE], m[WireKey.GAME_ERROR_CODE], m[WireKey.WAIT_ID]) for m in conns[0].sent_messages
        ] == [(EVENT_TYPE_INT[EventType.ERROR], GameErrorCode.INVALID_PASS, refused_wait)]
        assert current_wait_id(manager, conns[0]) == refused_wait

        await manager.shutdown()

    @pytest.mark.parametrize(
        ("answer", "error_code"),
        [
            (Pon(), GameErrorCode.INVALID_PON),
            (Kan(kan_type=KanType.OPEN, tile=-1), GameErrorCode.INVALID_KAN),
        ],
        ids=["pon", "open_kan"],
    )
    async def test_called_tile__when_a_call_names_another_copy_than_its_call__should_refuse_it_and_keep_the_call_open(
        self, real_engine, answer: Action, error_code: GameErrorCode
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice, bob = (participant_of(manager, conn).seat for conn in conns)
        discarded_four_pin = arrange_pon_now_and_on_the_next_draw(runtime_of(manager), discarder=alice, caller=bob)
        manager.handle_game_action(
            conns[0],
            action=Discard(tile=discarded_four_pin),
            called_tile=None,
            wait_id=current_wait_id(manager, conns[0]),
        )
        call_wait = current_wait_id(manager, conns[1])
        state_before = runtime_of(manager).state
        awaiting_before = manager.get_game("game1").awaiting
        conns[1]._outbox.clear()

        other_four_pin = discarded_four_pin + 1
        if isinstance(answer, Kan):
            answer = Kan(kan_type=KanType.OPEN, tile=other_four_pin)

        manager.handle_game_action(conns[1], action=answer, called_tile=other_four_pin, wait_id=call_wait)
        assert [
            (m[WireKey.EVENT_TYPE], m[WireKey.GAME_ERROR_CODE], m[WireKey.GAME_ERROR_MESSAGE], m[WireKey.WAIT_ID])
            for m in conns[1].sent_messages
        ] == [(EVENT_TYPE_INT[EventType.ERROR], error_code, "tile_id mismatch", call_wait)]
        assert runtime_of(manager).state is state_before
        assert manager.get_game("game1").awaiting is awaiting_before

        await manager.shutdown()


class TestStaleAction:
    async def test_stale_action__when_a_discard_raced_its_own_turn_timeout__should_be_refused_with_nothing_changed(
        self, real_engine
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        router = MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)
        conns = create_started_game(manager, player_names=["Alice"])
        alice = conns[0]
        alice_seat = participant_of(manager, alice).seat
        timed_out_wait = current_wait_id(manager, conns[0])
        timed_out_draw = runtime_of(manager).state.round_state.players[alice_seat].tiles[-1]
        await fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        state_before = runtime_of(manager).state
        awaiting_before = manager.get_game("game1").awaiting
        deadline = participant_of(manager, alice).timer.task
        alice._outbox.clear()

        router.handle_message(
            alice,
            {
                WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
                WireKey.WAIT_ID: timed_out_wait,
                WireKey.ACTION: WireGameAction.DISCARD,
                WireKey.TILE_ID: timed_out_draw,
            },
        )
        assert [
            (m[WireKey.EVENT_TYPE], m[WireKey.GAME_ERROR_CODE], m[WireKey.WAIT_ID]) for m in alice.sent_messages
        ] == [(EVENT_TYPE_INT[EventType.ERROR], GameErrorCode.STALE_ACTION, timed_out_wait)]
        assert not alice.is_closed
        assert runtime_of(manager).state is state_before
        assert manager.get_game("game1").awaiting is awaiting_before
        assert participant_of(manager, alice).timer.task is deadline

        await manager.shutdown()

    async def test_stale_action__when_a_pass_arrives_after_a_newer_prompt_opened__should_leave_that_prompt_pending(
        self, real_engine
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice, bob = (participant_of(manager, conn).seat for conn in conns)
        discarded_four_pin = arrange_pon_now_and_on_the_next_draw(runtime_of(manager), discarder=alice, caller=bob)
        manager.handle_game_action(
            conns[0],
            action=Discard(tile=discarded_four_pin),
            called_tile=None,
            wait_id=current_wait_id(manager, conns[0]),
        )
        first_prompt = manager.get_game("game1").awaiting
        first_prompt_id = current_wait_id(manager, conns[1])
        assert first_prompt == Call(seats=frozenset({bob}))

        run_timeout(manager, game_id="game1", timeout_type=TimeoutType.MELD, seat=bob)
        newer_prompt = manager.get_game("game1").awaiting
        assert newer_prompt == Call(seats=frozenset({bob}))
        assert current_wait_id(manager, conns[1]) == first_prompt_id + 1
        state_before = runtime_of(manager).state
        conns[1]._outbox.clear()

        manager.handle_game_action(conns[1], action=Pass(), called_tile=None, wait_id=first_prompt_id)
        assert [m[WireKey.GAME_ERROR_CODE] for m in conns[1].sent_messages] == [GameErrorCode.STALE_ACTION]
        assert runtime_of(manager).state is state_before
        assert bob in state_before.round_state.pending_call_prompt.pending_seats

        await manager.shutdown()
