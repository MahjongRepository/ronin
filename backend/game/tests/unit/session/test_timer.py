import asyncio

import pytest

from game.session.timer import TimerConfig, TurnTimer

BASE_AND_BANK = TimerConfig(base_turn_seconds=5, initial_bank_seconds=20)


def _noop() -> None:
    pass


def _recording_callback(calls: list[str], name: str):
    def on_timeout() -> None:
        calls.append(name)

    return on_timeout


class TestTurnTimerDeadline:
    async def test_turn_timer__when_bank_exhausted__should_fire_callback(self):
        timer = TurnTimer(TimerConfig(base_turn_seconds=0, initial_bank_seconds=0.05))
        callback_called = asyncio.Event()

        def on_timeout():
            callback_called.set()

        timer.start_decision_timer(on_timeout)
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)
        assert callback_called.is_set()

    async def test_turn_timer__when_base_and_bank_set__should_sleep_for_their_sum(self, held_sleep):
        timer = TurnTimer(BASE_AND_BANK)
        calls: list[str] = []

        timer.start_decision_timer(_recording_callback(calls, "timeout"))
        await asyncio.sleep(0)
        assert held_sleep.durations == [25.0]

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
        timer = TurnTimer(BASE_AND_BANK, clock=fake_clock.monotonic)

        timer.start_decision_timer(_noop)
        fake_clock.advance(elapsed)
        timer.stop()
        assert timer._bank_seconds == bank_after

    async def test_fixed_timer__when_stopped__should_keep_bank_unchanged(self, fake_clock, held_sleep):
        timer = TurnTimer(BASE_AND_BANK, clock=fake_clock.monotonic)

        timer.start_fixed_timer(10, _noop)
        fake_clock.advance(8)
        timer.stop()
        assert timer._bank_seconds == 20.0


class TestTurnTimerCancel:
    async def test_turn_timer__when_stopped__should_not_fire_callback(self, held_sleep):
        timer = TurnTimer(BASE_AND_BANK)
        calls: list[str] = []

        timer.start_decision_timer(_recording_callback(calls, "timeout"))
        sleeping = timer.task
        timer.stop()
        await asyncio.sleep(0)
        assert sleeping.cancelled()

        await held_sleep.release_all()
        assert calls == []

    async def test_turn_timer__when_new_timer_started__should_cancel_previous_callback(self, held_sleep):
        timer = TurnTimer(BASE_AND_BANK)
        calls: list[str] = []

        timer.start_decision_timer(_recording_callback(calls, "first"))
        first = timer.task
        timer.start_decision_timer(_recording_callback(calls, "second"))
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

        def restart():
            timer.start_decision_timer(_noop)
            finished.append("callback")

        timer.start_decision_timer(restart)
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


class TestBankReset:
    @pytest.mark.parametrize("elapsed", [0, 7.5, 40])
    async def test_reset_bank__when_a_new_hand_starts__should_restore_exactly_the_full_bank(
        self, fake_clock, held_sleep, elapsed
    ):
        timer = TurnTimer(BASE_AND_BANK, clock=fake_clock.monotonic)
        timer.start_decision_timer(_noop)
        fake_clock.advance(elapsed)
        timer.stop()

        timer.reset_bank()
        assert timer.bank_seconds == 20
