import asyncio
import logging
import threading
from functools import partial
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from game.engine import (
    Call,
    Discard,
    DoubleRonResult,
    DoubleRonWinner,
    EventType,
    HandLimit,
    HandResultInfo,
    Kan,
    KanType,
    Pass,
    Pon,
    Refusal,
    RefusalCode,
    RefusalKind,
    RoundEndEvent,
    RoundOver,
    Turn,
    YakuInfo,
)
from game.messaging.game_errors import GameErrorCode
from game.messaging.types import SessionErrorCode
from game.session.manager import SessionManager
from game.session.models import GameLifecycle, GameSession, Participant, Pause, PlayerSpec
from game.session.timer import TimeoutType, TimerConfig, TurnTimer
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import FakeGameRepository, MockConnection
from game.tests.unit.logic.helpers import _update_player
from game.wire.compact import decode_draw
from game.wire.events import EVENT_TYPE_INT
from game.wire.keys import WireKey
from shared.dal.models import GameEndReason
from shared.storage import LocalReplayStorage, replay_file_path

from .helpers import (
    ENGINE_SEED,
    arrange_exhaustive_draw,
    arrange_final_discard,
    arrange_ron_and_pon_on_a_discard,
    create_started_game,
    current_wait_id,
    fire_turn_timer_now,
    game_of,
    participant_of,
    run_timeout,
    runtime_of,
    wait_for_background_tasks,
)

if TYPE_CHECKING:
    from pathlib import Path


ARMING_CONFIG = TimerConfig(base_turn_seconds=5, initial_bank_seconds=20)
HAKU_COPIES = [tile_copies(copy, honors="5")[0] for copy in range(4)]


def _double_ron_round_end() -> RoundEndEvent:
    hand_result = HandResultInfo(limit=HandLimit.NONE, han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)], points=1000)
    scores = dict.fromkeys(range(4), 25000)
    winners = [
        DoubleRonWinner(
            honba_bonus=0,
            winner_seat=seat,
            hand_result=hand_result,
            score_changes=scores,
            riichi_sticks_collected=0,
            closed_tiles=[],
            melds=[],
        )
        for seat in (2, 3)
    ]
    result = DoubleRonResult(loser_seat=1, winning_tile=0, winners=winners, scores=scores, score_changes=scores)
    return RoundEndEvent(dealer_seat=0, dora_indicators=[], riichi_sticks=0, result=result)


def _arm_double_ron_round_over_pause(manager: SessionManager, participant: Participant) -> None:
    participant.connection = MockConnection()
    participant.game.participants.append(participant)
    manager._open_round_over_pause(participant.game, [_double_ron_round_end()])
    manager._start_wait_timers(participant.game, awaiting=RoundOver())


class TestWaitTimerArming:
    @pytest.fixture
    def participant(self):
        game = GameSession(game_id="g1", timer_config=ARMING_CONFIG)
        return Participant(
            spec=PlayerSpec(name="Alice", user_id="user-0", game_ticket="ticket-0"),
            game=game,
            timer=TurnTimer(ARMING_CONFIG),
            seat=0,
        )

    @pytest.mark.parametrize(
        "arming",
        [
            (SessionManager._start_turn_timer, TimeoutType.TURN, 25.0),
            (SessionManager._start_meld_timer, TimeoutType.MELD, 25.0),
            (
                partial(SessionManager._start_pause_timer, pause=Pause(starts_game=False, seats=frozenset({0}))),
                TimeoutType.ROUND_ADVANCE,
                ARMING_CONFIG.round_advance_timeout_seconds,
            ),
            (
                partial(SessionManager._start_pause_timer, pause=Pause(starts_game=True, seats=frozenset({0}))),
                TimeoutType.ROUND_ADVANCE,
                ARMING_CONFIG.game_start_confirm_seconds,
            ),
            (
                _arm_double_ron_round_over_pause,
                TimeoutType.ROUND_ADVANCE,
                2 * ARMING_CONFIG.round_advance_timeout_seconds,
            ),
        ],
    )
    async def test_wait_timer__when_an_armed_timer_expires__should_report_its_participant_and_timeout_type(
        self, participant, held_sleep, monkeypatch, arming
    ):
        manager = make_session_manager()
        timeout_log = []
        monkeypatch.setattr(manager, "_handle_timeout", lambda *timed_out: timeout_log.append(timed_out))
        monkeypatch.setattr(
            manager,
            "_handle_pause_timeout",
            lambda timed_out: timeout_log.append((timed_out, TimeoutType.ROUND_ADVANCE)),
        )
        start, timeout_type, duration = arming
        start(manager, participant)
        await asyncio.sleep(0)
        assert held_sleep.durations == [duration]

        await held_sleep.release_all()
        assert timeout_log == [(participant, timeout_type)]


class TestSessionManagerTimers:
    async def test_handle_timeout__when_turn_times_out__should_broadcast_resulting_events(self, manager):
        conns = create_started_game(manager)
        conns[0]._outbox.clear()

        run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=0)
        timeout_msgs = [
            m
            for m in conns[0].sent_messages
            if m.get(WireKey.EVENT_TYPE) == EVENT_TYPE_INT[EventType.DRAW]
            and decode_draw(m[WireKey.PACKED_MOVE])[0] == 0
        ]
        assert len(timeout_msgs) == 1
        assert (manager.stats["timeouts_turn"], manager.stats["timeouts_meld"]) == (1, 0)


class TestWaitTimers:
    async def test_turn_timer__when_the_players_action_is_refused__should_keep_the_running_deadline(self, real_engine):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        conns = create_started_game(manager, player_names=["Alice"])
        timer = participant_of(manager, conns[0]).timer
        deadline, bank = timer.task, timer._bank_seconds

        manager.handle_game_action(
            conns[0], action=Pass(), called_tile=None, wait_id=current_wait_id(manager, conns[0])
        )
        assert [m[WireKey.GAME_ERROR_CODE] for m in conns[0].sent_messages] == [GameErrorCode.INVALID_PASS]
        assert timer.task is deadline
        assert not deadline.done()
        assert timer._bank_seconds == bank

        await manager.shutdown()

    async def test_meld_timers__when_one_of_two_callers_passes__should_keep_the_other_callers_deadline(
        self, real_engine, fake_clock
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED, clock=fake_clock.monotonic)
        conns = create_started_game(manager, player_names=["Alice", "Bob", "Carol"])
        alice, bob, carol = (participant_of(manager, conn).seat for conn in conns)
        discarded_four_pin = arrange_ron_and_pon_on_a_discard(runtime_of(manager), discarder=alice, ron=bob, pon=carol)

        manager.handle_game_action(
            conns[0],
            action=Discard(tile=discarded_four_pin),
            called_tile=None,
            wait_id=current_wait_id(manager, conns[0]),
        )
        prompt = manager.get_game("game1").awaiting
        assert prompt == Call(seats=frozenset({bob, carol}))
        carol_timer = participant_of(manager, conns[2]).timer
        carol_deadline = carol_timer.task
        prompt_message = next(
            m for m in conns[2].sent_messages if m.get(WireKey.EVENT_TYPE) == EVENT_TYPE_INT[EventType.CALL_PROMPT]
        )
        assert prompt_message[WireKey.BANK_SECONDS] == 20
        fake_clock.advance(7)

        manager.handle_game_action(
            conns[1], action=Pass(), called_tile=None, wait_id=current_wait_id(manager, conns[1])
        )
        assert manager.get_game("game1").awaiting == Call(seats=frozenset({carol}))
        assert participant_of(manager, conns[1]).timer.task is None
        assert carol_timer.task is carol_deadline
        assert not carol_deadline.done()
        assert participant_of(manager, conns[1]).timer.bank_seconds == 18

        fake_clock.advance(2)
        manager.handle_game_action(
            conns[2], action=Pon(), called_tile=discarded_four_pin, wait_id=prompt_message[WireKey.WAIT_ID]
        )
        assert carol_timer.bank_seconds == 16
        turn = next(m for m in conns[2].sent_messages if m.get(WireKey.EVENT_TYPE) == EVENT_TYPE_INT[EventType.TURN])
        assert turn[WireKey.BANK_SECONDS] == 16

        await manager.shutdown()

    async def test_turn_timer__when_a_closed_kan_returns_the_turn_to_the_seat__should_open_a_new_decision(
        self, real_engine
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice = participant_of(manager, conns[0])
        assert game_of(manager).awaiting.seats == frozenset({alice.seat})
        hand = runtime_of(manager).state.round_state.players[alice.seat].tiles
        _update_player(
            runtime_of(manager),
            seat=alice.seat,
            tiles=(*[tile for tile in hand if tile not in HAKU_COPIES][:10], *HAKU_COPIES),
        )
        kan_decision, kan_deadline = alice.decision_id, alice.timer.task

        manager.handle_game_action(
            conns[0], action=Kan(kan_type=KanType.CLOSED, tile=HAKU_COPIES[0]), called_tile=None, wait_id=kan_decision
        )
        awaiting = game_of(manager).awaiting
        assert awaiting == Turn(seat=alice.seat)
        assert alice.decision_id == kan_decision + 1
        [replacement_draw] = [
            m for m in conns[0].sent_messages if m.get(WireKey.EVENT_TYPE) == EVENT_TYPE_INT[EventType.DRAW]
        ]
        assert replacement_draw[WireKey.WAIT_ID] == kan_decision + 1
        assert alice.timer.task not in (None, kan_deadline)

        await manager.shutdown()

    async def test_call_bank__when_callers_time_out__should_exhaust_their_reserves_and_pass(
        self, real_engine, fake_clock, held_sleep
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED, clock=fake_clock.monotonic)
        conns = create_started_game(manager, player_names=["Alice", "Bob", "Carol"])
        alice, bob, carol = (participant_of(manager, conn) for conn in conns)
        discarded_four_pin = arrange_ron_and_pon_on_a_discard(
            runtime_of(manager), discarder=alice.seat, ron=bob.seat, pon=carol.seat
        )
        manager.handle_game_action(
            conns[0],
            action=Discard(tile=discarded_four_pin),
            called_tile=None,
            wait_id=current_wait_id(manager, conns[0]),
        )
        assert game_of(manager).awaiting.seats == frozenset({bob.seat, carol.seat})
        await asyncio.sleep(0)
        assert held_sleep.durations == [25, 25]
        fake_clock.advance(25)

        await held_sleep.release_all()
        assert isinstance(game_of(manager).awaiting, Turn)
        assert (bob.timer.bank_seconds, carol.timer.bank_seconds) == (0, 0)

        await manager.shutdown()

    async def test_round_bank__when_rounds_start_and_end__should_reset_once_before_the_first_draw(
        self, real_engine, fake_clock
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED, clock=fake_clock.monotonic)
        conns = create_started_game(manager, player_names=["Alice"])
        alice_seat = participant_of(manager, conns[0]).seat
        timer = participant_of(manager, conns[0]).timer
        config = TimerConfig()
        first_round_bank = config.initial_bank_seconds
        assert timer.bank_seconds == first_round_bank
        fake_clock.advance(7)

        arrange_exhaustive_draw(runtime_of(manager))
        drawn_tile = runtime_of(manager).state.round_state.players[alice_seat].tiles[-1]
        manager.handle_game_action(
            conns[0], action=Discard(tile=drawn_tile), called_tile=None, wait_id=current_wait_id(manager, conns[0])
        )
        assert manager.get_game("game1").awaiting == RoundOver()
        assert timer.bank_seconds == first_round_bank - 2

        conns[0]._outbox.clear()
        manager.confirm_round(conns[0], wait_id=current_wait_id(manager, conns[0]))
        second_round = manager.get_game("game1").awaiting
        second_round_decision = current_wait_id(manager, conns[0])
        assert (runtime_of(manager).state.round_number, second_round.seats) == (1, frozenset({alice_seat}))
        assert timer._bank_seconds == first_round_bank
        opening_draw = next(
            m for m in conns[0].sent_messages if m.get(WireKey.EVENT_TYPE) == EVENT_TYPE_INT[EventType.DRAW]
        )
        assert opening_draw[WireKey.BANK_SECONDS] == first_round_bank

        fake_clock.advance(8)
        if isinstance(second_round, Call):
            manager.handle_game_action(
                conns[0], action=Pass(), called_tile=None, wait_id=current_wait_id(manager, conns[0])
            )
        else:
            drawn_tile = runtime_of(manager).state.round_state.players[alice_seat].tiles[-1]
            manager.handle_game_action(
                conns[0], action=Discard(tile=drawn_tile), called_tile=None, wait_id=current_wait_id(manager, conns[0])
            )
        assert runtime_of(manager).state.round_number == 1
        assert current_wait_id(manager, conns[0]) == second_round_decision + 1
        assert timer.bank_seconds == first_round_bank - 3

        await manager.shutdown()

    async def test_round_bank__when_a_round_starts_while_a_participant_is_away__should_reset_their_bank(
        self, real_engine
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice, bob = (participant_of(manager, conn) for conn in conns)
        first_round_bank = TimerConfig().initial_bank_seconds
        assert (alice.timer._bank_seconds, bob.timer._bank_seconds) == (first_round_bank, first_round_bank)
        manager.disconnect(conns[1])
        bob.timer._bank_seconds = 3
        game = game_of(manager)
        assert game.awaiting == Turn(seat=alice.seat)

        arrange_exhaustive_draw(runtime_of(manager))
        drawn_tile = runtime_of(manager).state.round_state.players[alice.seat].tiles[-1]
        manager.handle_game_action(
            conns[0], action=Discard(tile=drawn_tile), called_tile=None, wait_id=current_wait_id(manager, conns[0])
        )
        manager.confirm_round(conns[0], wait_id=current_wait_id(manager, conns[0]))
        assert runtime_of(manager).state.round_number == 1
        assert alice.timer._bank_seconds == first_round_bank

        reconnecting = MockConnection()
        manager.register_connection(reconnecting)
        manager.reconnect(reconnecting, session_token=bob.ticket)
        assert bob.connection is reconnecting
        assert bob.timer._bank_seconds == first_round_bank

        await manager.shutdown()


class _GatedReplayStorage(LocalReplayStorage):
    def __init__(self, replay_dir: Path) -> None:
        super().__init__(replay_dir)
        self.save_started = threading.Event()
        self.may_finish = threading.Event()

    def save_replay(self, game_id: str, content: bytes) -> None:
        self.save_started.set()
        self.may_finish.wait(timeout=5)
        super().save_replay(game_id, content)


def _discard_the_drawn_tile(manager: SessionManager, participant: Participant) -> None:
    drawn_tile = runtime_of(manager).state.round_state.players[participant.seat].tiles[-1]
    manager.handle_game_action(
        participant.connection,
        action=Discard(tile=drawn_tile),
        called_tile=None,
        wait_id=current_wait_id(manager, participant.connection),
    )


def _disconnect(manager: SessionManager, participant: Participant) -> None:
    manager.disconnect(participant.connection)


class TestTimerCallbackLifecycle:
    @pytest.mark.parametrize(
        ("player_names", "end_the_wait"),
        [(["Alice"], _discard_the_drawn_tile), (["Alice", "Bob"], _disconnect)],
        ids=["own_discard", "disconnect"],
    )
    async def test_turn_timeout__when_the_wait_ends_after_its_sleep_but_before_it_ran__should_drop_the_default_action(
        self, real_engine, held_sleep, player_names, end_the_wait
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        create_started_game(manager, player_names=player_names)
        game = game_of(manager)
        [awaited_seat] = game.awaiting.seats
        awaited = game.at_seat(awaited_seat)
        await asyncio.sleep(0)
        slept = awaited.timer.task
        assert len(held_sleep.durations) == 1

        held_sleep.wake_all()
        end_the_wait(manager, awaited)
        await asyncio.wait({slept})
        assert game.lifecycle is GameLifecycle.PLAYING
        assert len(runtime_of(manager).state.round_state.players[awaited_seat].discards) == 1
        successor = game.at_seat(min(game.awaiting.seats))
        assert successor.timer.task not in (None, slept)

        await manager.shutdown()

    async def test_turn_timeout__when_ai_turns_lead_back_to_the_human__should_keep_the_successor_timer_armed(
        self, real_engine
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        conns = create_started_game(manager, player_names=["Alice"])
        alice_seat = participant_of(manager, conns[0]).seat
        timer = participant_of(manager, conns[0]).timer
        timed_out = manager.get_game("game1").awaiting
        timed_out_decision = current_wait_id(manager, conns[0])

        fired = fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await fired
        successor = manager.get_game("game1").awaiting
        assert successor == timed_out
        assert current_wait_id(manager, conns[0]) == timed_out_decision + 1
        draws_after_timeout = [
            m for m in conns[0].sent_messages if m.get(WireKey.EVENT_TYPE) == EVENT_TYPE_INT[EventType.DRAW]
        ]
        assert len(draws_after_timeout) == 1
        assert timer.task is not None
        assert timer.task is not fired
        assert not timer.task.done()

        await manager.shutdown()

    async def test_turn_timeout__when_armed_by_another_seats_discard__should_log_as_its_own_seat(
        self, real_engine, held_sleep, caplog
    ):
        manager = make_session_manager(real_engine, seed=ENGINE_SEED)
        create_started_game(manager, player_names=["Alice", "Bob"])
        game = game_of(manager)
        [discarder_seat] = game.awaiting.seats
        _discard_the_drawn_tile(manager, game.at_seat(discarder_seat))
        [timed_out_seat] = game.awaiting.seats
        assert (isinstance(game.awaiting, Turn), timed_out_seat != discarder_seat) == (True, True)

        await asyncio.sleep(0)
        with caplog.at_level(logging.INFO):
            await held_sleep.release_all()
        auto_discards = [r.msg for r in caplog.records if r.msg["event"] == "turn timeout, auto-discarding"]
        assert [(log["game_id"], log["seat"]) for log in auto_discards] == [("game1", timed_out_seat)]

        await manager.shutdown()

    async def test_turn_timeout__when_the_engine_refuses_the_default_action__should_fail_the_game_instead_of_stalling(
        self, real_engine, tmp_path
    ):
        game_repo = FakeGameRepository()
        manager = make_session_manager(
            real_engine, seed=ENGINE_SEED, repository=game_repo, storage=LocalReplayStorage(tmp_path)
        )
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = participant_of(manager, conns[0]).seat
        real_engine.act = MagicMock(
            return_value=Refusal(kind=RefusalKind.NOT_OFFERED, code=RefusalCode.TILE_NOT_HELD),
        )

        await fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert game_repo.games["game1"].end_reason == GameEndReason.ERROR
        assert replay_file_path(tmp_path, "game1").exists()
        for conn in conns:
            assert [m[WireKey.SESSION_ERROR_CODE] for m in conn.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
            assert conn._close_code == 1011

    async def test_shutdown__when_a_game_end_is_suspended_in_its_replay_save__should_wait_for_it_and_leave_no_task(
        self, real_engine, tmp_path
    ):
        game_repo = FakeGameRepository()
        storage = _GatedReplayStorage(tmp_path)
        manager = make_session_manager(real_engine, seed=ENGINE_SEED, repository=game_repo, storage=storage)
        conns = create_started_game(manager, player_names=["Alice"])
        alice_seat = participant_of(manager, conns[0]).seat
        arrange_final_discard(runtime_of(manager), seat=alice_seat)
        fired = fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        assert await asyncio.to_thread(storage.save_started.wait, 5)

        shutdown = asyncio.create_task(manager.shutdown())
        await asyncio.sleep(0)
        assert not shutdown.done()

        storage.may_finish.set()
        await shutdown
        assert fired.done()
        assert not fired.cancelled()
        assert game_repo.games["game1"].end_reason == GameEndReason.COMPLETED
        assert conns[0]._close_code == 1000
        assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()] == []
