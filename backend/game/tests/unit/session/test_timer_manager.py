import asyncio

import pytest

from game.logic.enums import TimeoutType
from game.session.models import GameSession, Participant, PlayerSpec
from game.session.timer import TimerConfig, TurnTimer
from game.session.timer_manager import TimerFiring, TimerManager

CONFIG = TimerConfig(base_turn_seconds=5, initial_bank_seconds=20, meld_decision_seconds=3)


@pytest.fixture
def timeout_log():
    return []


@pytest.fixture
def timer_manager(timeout_log):
    async def on_timeout(participant: Participant, timeout_type: TimeoutType, firing: TimerFiring) -> None:
        timeout_log.append((participant, timeout_type, firing))

    return TimerManager(on_timeout=on_timeout)


@pytest.fixture
def participant():
    game = GameSession(game_id="g1", timer_config=CONFIG)
    return Participant(
        spec=PlayerSpec(name="Alice", user_id="user-0", game_ticket="ticket-0"),
        game=game,
        timer=TurnTimer(CONFIG),
        seat=0,
    )


class TestTimerManagerArming:
    @pytest.mark.parametrize(
        "arming",
        [
            (TimerManager.start_turn_timer, TimeoutType.TURN, 25.0),
            (TimerManager.start_meld_timer, TimeoutType.MELD, 3),
            (TimerManager.start_round_advance_timer, TimeoutType.ROUND_ADVANCE, CONFIG.round_advance_timeout_seconds),
        ],
    )
    async def test_timer_manager__when_an_armed_timer_expires__should_report_its_participant_and_timeout_type(
        self, timer_manager, timeout_log, participant, held_sleep, arming
    ):
        start, timeout_type, duration = arming
        start(timer_manager, participant)
        await asyncio.sleep(0)
        assert held_sleep.durations == [duration]

        await held_sleep.release_all()
        [(reported, reported_type, firing)] = timeout_log
        assert (reported, reported_type) == (participant, timeout_type)
        assert firing.is_superseded is False

    async def test_timer_firing__when_its_timer_is_rearmed_after_firing__should_be_superseded(
        self, timer_manager, timeout_log, participant, held_sleep
    ):
        timer_manager.start_turn_timer(participant)
        await asyncio.sleep(0)
        await held_sleep.release_all()
        [(_reported, _type, firing)] = timeout_log

        participant.timer.cancel()
        assert firing.is_superseded is True
