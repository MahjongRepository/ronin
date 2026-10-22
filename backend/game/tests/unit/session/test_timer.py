import asyncio

import pytest
from pydantic import ValidationError

from game.session.timer import TimerConfig, TurnTimer

BASE_AND_BANK = TimerConfig(base_turn_seconds=5, initial_bank_seconds=20)


async def _noop() -> None:
    pass


def _recording_callback(calls: list[str], name: str):
    async def on_timeout() -> None:
        calls.append(name)

    return on_timeout


def test_timer_config__when_max_bank_below_initial_bank__should_raise():
    with pytest.raises(ValidationError, match="max_bank_seconds must be >= initial_bank_seconds"):
        TimerConfig(max_bank_seconds=5, initial_bank_seconds=20)


class TestTurnTimerDeadline:
    async def test_turn_timer__when_bank_exhausted__should_fire_callback(self):
        timer = TurnTimer(TimerConfig(base_turn_seconds=0, initial_bank_seconds=0.05))
        callback_called = asyncio.Event()

        async def on_timeout():
            callback_called.set()

        timer.start_turn_timer(on_timeout)
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)
        assert callback_called.is_set()

    async def test_turn_timer__when_base_and_bank_set__should_sleep_for_their_sum(self, held_sleep):
        timer = TurnTimer(BASE_AND_BANK)
        calls: list[str] = []

        timer.start_turn_timer(_recording_callback(calls, "timeout"))
        await asyncio.sleep(0)
        assert held_sleep.durations == [25.0]

        await held_sleep.release_all()
        assert calls == ["timeout"]

    async def test_meld_timer__when_started__should_sleep_for_the_fixed_meld_time(self, held_sleep):
        timer = TurnTimer(TimerConfig(meld_decision_seconds=3))
        calls: list[str] = []

        timer.start_meld_timer(_recording_callback(calls, "timeout"))
        await asyncio.sleep(0)
        assert held_sleep.durations == [3]

        await held_sleep.release_all()
        assert calls == ["timeout"]


class TestTurnTimerBank:
    @pytest.mark.parametrize(
        ("elapsed", "bank_after"),
        [(3.0, 20.0), (7.5, 17.5), (40.0, 0.0)],
    )
    async def test_turn_timer__when_stopped__should_drain_only_the_time_past_base_from_the_bank(
        self, fake_clock, held_sleep, elapsed, bank_after
    ):
        timer = TurnTimer(BASE_AND_BANK)

        timer.start_turn_timer(_noop)
        fake_clock.advance(elapsed)
        timer.stop()
        assert timer._bank_seconds == bank_after

    async def test_meld_timer__when_cancelled__should_keep_bank_unchanged(self, fake_clock, held_sleep):
        timer = TurnTimer(BASE_AND_BANK)

        timer.start_meld_timer(_noop)
        fake_clock.advance(4)
        timer.cancel()
        assert timer._bank_seconds == 20.0


class TestTurnTimerCancel:
    async def test_turn_timer__when_stopped__should_not_fire_callback(self, held_sleep):
        timer = TurnTimer(BASE_AND_BANK)
        calls: list[str] = []

        timer.start_turn_timer(_recording_callback(calls, "timeout"))
        sleeping = timer.task
        timer.stop()
        await asyncio.sleep(0)
        assert sleeping.cancelled()

        await held_sleep.release_all()
        assert calls == []

    async def test_turn_timer__when_new_timer_started__should_cancel_previous_callback(self, held_sleep):
        timer = TurnTimer(BASE_AND_BANK)
        calls: list[str] = []

        timer.start_turn_timer(_recording_callback(calls, "first"))
        first = timer.task
        timer.start_turn_timer(_recording_callback(calls, "second"))
        await asyncio.sleep(0)
        assert first.cancelled()

        await held_sleep.release_all()
        assert calls == ["second"]


class TestTimerCallbackOwnership:
    async def test_turn_timer__when_callback_restarts_its_own_timer__should_finish_and_keep_the_successor(
        self, held_sleep
    ):
        timer = TurnTimer(BASE_AND_BANK)
        finished: list[str] = []

        async def restart_then_suspend():
            timer.start_meld_timer(_noop)
            await asyncio.sleep(0)
            finished.append("callback")

        timer.start_turn_timer(restart_then_suspend)
        fired = timer.task
        assert fired is not None

        await asyncio.sleep(0)
        await held_sleep.release_all()
        await fired
        assert finished == ["callback"]
        assert timer.task is not None
        assert timer.task is not fired
        assert not timer.task.done()
        timer.cancel()


class TestBankCap:
    def test_round_bonus__when_exceeding_max_bank__should_cap_at_max(self):
        timer = TurnTimer(TimerConfig(initial_bank_seconds=55.0, max_bank_seconds=60.0, round_bonus_seconds=10.0))

        timer.add_round_bonus()
        assert timer._bank_seconds == 60.0

    def test_round_bonus__when_below_cap__should_add_full_bonus(self):
        timer = TurnTimer(TimerConfig(initial_bank_seconds=10.0, max_bank_seconds=60.0, round_bonus_seconds=10.0))

        timer.add_round_bonus()
        assert timer._bank_seconds == 20.0
