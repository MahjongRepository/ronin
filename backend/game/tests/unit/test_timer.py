import asyncio

from game.logic.timer import TimerConfig, TurnTimer


async def _noop() -> None:
    pass


class TestTurnTimerTurnTimer:
    async def test_turn_timer__when_bank_exhausted__should_fire_callback(self):
        config = TimerConfig(base_turn_seconds=0, initial_bank_seconds=0.05)
        timer = TurnTimer(config)
        callback_called = asyncio.Event()

        async def on_timeout():
            callback_called.set()

        timer.start_turn_timer(on_timeout)
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)
        assert callback_called.is_set()

    async def test_turn_timer__when_stopped__should_deduct_elapsed_time_from_bank(self):
        config = TimerConfig(base_turn_seconds=0, initial_bank_seconds=10.0)
        timer = TurnTimer(config)

        timer.start_turn_timer(_noop)
        await asyncio.sleep(0.1)
        timer.stop()
        # bank should be reduced by approximately 0.1 seconds
        assert timer._bank_seconds < 10.0
        assert timer._bank_seconds > 9.0

    async def test_turn_timer__when_stopped__should_not_fire_callback(self):
        timer = TurnTimer()
        callback_called = False

        async def on_timeout():
            nonlocal callback_called
            callback_called = True

        timer.start_turn_timer(on_timeout)
        timer.stop()
        await asyncio.sleep(0.05)
        assert callback_called is False


class TestTurnTimerMeldTimer:
    async def test_meld_timer__when_started__should_fire_after_fixed_timeout(self):
        config = TimerConfig(meld_decision_seconds=0.05)
        timer = TurnTimer(config)
        callback_called = asyncio.Event()

        async def on_timeout():
            callback_called.set()

        timer.start_meld_timer(on_timeout)
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)
        assert callback_called.is_set()

    async def test_meld_timer__when_cancelled__should_keep_bank_unchanged(self):
        config = TimerConfig(initial_bank_seconds=10.0)
        timer = TurnTimer(config)

        timer.start_meld_timer(_noop)
        await asyncio.sleep(0.05)
        timer.cancel()
        # bank time should not change for meld timers
        assert timer._bank_seconds == 10.0


class TestTurnTimerBankEdgeCases:
    async def test_turn_timer__when_running_past_bank__should_clamp_bank_at_zero(self):
        config = TimerConfig(base_turn_seconds=0, initial_bank_seconds=0.05)
        timer = TurnTimer(config)

        timer.start_turn_timer(_noop)
        await asyncio.sleep(0.15)
        timer.stop()
        assert timer._bank_seconds == 0.0

    async def test_turn_timer__when_new_timer_started__should_cancel_previous_callback(self):
        timer = TurnTimer()
        first_called = False
        second_called = False

        async def first_callback():
            nonlocal first_called
            first_called = True

        async def second_callback():
            nonlocal second_called
            second_called = True

        timer.start_turn_timer(first_callback)
        timer.start_turn_timer(second_callback)
        await asyncio.sleep(0.05)
        timer.cancel()
        assert first_called is False


class TestTimerCallbackOwnership:
    async def test_turn_timer__when_callback_restarts_its_own_timer__should_finish_and_keep_the_successor(self):
        timer = TurnTimer(TimerConfig(base_turn_seconds=0, initial_bank_seconds=0))
        finished: list[str] = []

        async def restart_then_suspend():
            timer.start_meld_timer(_noop)
            await asyncio.sleep(0)
            finished.append("callback")

        timer.start_turn_timer(restart_then_suspend)
        fired = timer.task
        assert fired is not None

        await fired
        assert finished == ["callback"]
        assert timer.task is not None
        assert timer.task is not fired
        assert not timer.task.done()
        timer.cancel()


class TestBaseTimeBehavior:
    async def test_turn_timer__when_acting_within_base_time__should_keep_bank(self):
        config = TimerConfig(base_turn_seconds=1.0, initial_bank_seconds=10.0)
        timer = TurnTimer(config)

        timer.start_turn_timer(_noop)
        await asyncio.sleep(0.1)  # well within 1s base time
        timer.stop()
        assert timer.bank_seconds == 10.0

    async def test_turn_timer__when_acting_after_base_time__should_drain_only_excess(self):
        config = TimerConfig(base_turn_seconds=0.1, initial_bank_seconds=10.0)
        timer = TurnTimer(config)

        timer.start_turn_timer(_noop)
        await asyncio.sleep(0.2)  # ~0.1s over base time
        timer.stop()
        # should drain ~0.1s from bank; wide tolerance for CI scheduling jitter
        assert 9.5 < timer.bank_seconds < 10.0

    async def test_turn_timer__when_base_and_bank_set__should_fire_after_their_sum(self):
        config = TimerConfig(base_turn_seconds=0.05, initial_bank_seconds=0.05)
        timer = TurnTimer(config)
        callback_called = asyncio.Event()

        async def on_timeout():
            callback_called.set()

        loop = asyncio.get_running_loop()
        started_at = loop.time()
        timer.start_turn_timer(on_timeout)
        # should fire at ~0.1s (0.05 base + 0.05 bank)
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)
        assert loop.time() - started_at >= 0.09


class TestBankCap:
    def test_round_bonus__when_exceeding_max_bank__should_cap_at_max(self):
        config = TimerConfig(
            initial_bank_seconds=55.0,
            max_bank_seconds=60.0,
            round_bonus_seconds=10.0,
        )
        timer = TurnTimer(config)

        timer.add_round_bonus()
        assert timer.bank_seconds == 60.0  # capped, not 65

    def test_round_bonus__when_below_cap__should_add_full_bonus(self):
        config = TimerConfig(
            initial_bank_seconds=10.0,
            max_bank_seconds=60.0,
            round_bonus_seconds=10.0,
        )
        timer = TurnTimer(config)

        timer.add_round_bonus()
        assert timer.bank_seconds == 20.0
