import asyncio

from game.logic.timer import TimerConfig, TurnTimer


class TestTurnTimerInit:
    def test_default_config(self):
        timer = TurnTimer()
        assert timer.remaining_bank == 30.0

    def test_custom_config(self):
        config = TimerConfig(initial_bank_seconds=60.0)
        timer = TurnTimer(config)
        assert timer.remaining_bank == 60.0


class TestTurnTimerRoundBonus:
    def test_add_round_bonus(self):
        config = TimerConfig(initial_bank_seconds=30.0, round_bonus_seconds=10.0)
        timer = TurnTimer(config)
        timer.add_round_bonus()
        assert timer.remaining_bank == 40.0

    def test_add_multiple_round_bonuses(self):
        config = TimerConfig(initial_bank_seconds=30.0, round_bonus_seconds=10.0)
        timer = TurnTimer(config)
        timer.add_round_bonus()
        timer.add_round_bonus()
        assert timer.remaining_bank == 50.0


class TestTurnTimerTurnTimer:
    async def test_start_turn_timer_creates_task(self):
        timer = TurnTimer()
        callback_called = False

        async def on_timeout():
            nonlocal callback_called
            callback_called = True

        timer.start_turn_timer(on_timeout)
        assert timer._active_task is not None
        assert not timer._active_task.done()
        timer.cancel()

    async def test_turn_timer_callback_fires_on_timeout(self):
        config = TimerConfig(initial_bank_seconds=0.05)
        timer = TurnTimer(config)
        callback_called = asyncio.Event()

        async def on_timeout():
            callback_called.set()

        timer.start_turn_timer(on_timeout)
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)
        assert callback_called.is_set()

    async def test_stop_deducts_elapsed_time(self):
        config = TimerConfig(initial_bank_seconds=10.0)
        timer = TurnTimer(config)

        async def on_timeout():
            pass

        timer.start_turn_timer(on_timeout)
        await asyncio.sleep(0.1)
        timer.stop()

        # bank should be reduced by approximately 0.1 seconds
        assert timer.remaining_bank < 10.0
        assert timer.remaining_bank > 9.0

    async def test_stop_cancels_pending_timer(self):
        timer = TurnTimer()
        callback_called = False

        async def on_timeout():
            nonlocal callback_called
            callback_called = True

        timer.start_turn_timer(on_timeout)
        task = timer._active_task
        timer.stop()

        await asyncio.sleep(0.05)
        assert callback_called is False
        assert task is not None
        assert task.cancelled()


class TestTurnTimerMeldTimer:
    async def test_start_meld_timer_uses_fixed_timeout(self):
        config = TimerConfig(meld_decision_seconds=0.05)
        timer = TurnTimer(config)
        callback_called = asyncio.Event()

        async def on_timeout():
            callback_called.set()

        timer.start_meld_timer(on_timeout)
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)
        assert callback_called.is_set()

    async def test_cancel_does_not_deduct_bank_time(self):
        config = TimerConfig(initial_bank_seconds=10.0)
        timer = TurnTimer(config)

        async def on_timeout():
            pass

        timer.start_meld_timer(on_timeout)
        await asyncio.sleep(0.05)
        timer.cancel()

        # bank time should not change for meld timers
        assert timer.remaining_bank == 10.0


class TestTurnTimerBankEdgeCases:
    async def test_bank_does_not_go_below_zero(self):
        config = TimerConfig(initial_bank_seconds=0.05)
        timer = TurnTimer(config)

        async def on_timeout():
            pass

        timer.start_turn_timer(on_timeout)
        await asyncio.sleep(0.15)
        timer.stop()
        assert timer.remaining_bank == 0.0

    async def test_remaining_bank_during_active_timer(self):
        config = TimerConfig(initial_bank_seconds=10.0)
        timer = TurnTimer(config)

        async def on_timeout():
            pass

        timer.start_turn_timer(on_timeout)
        await asyncio.sleep(0.1)
        # remaining bank should reflect elapsed time
        assert timer.remaining_bank < 10.0
        assert timer.remaining_bank > 9.0
        timer.cancel()

    async def test_starting_new_timer_cancels_previous(self):
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


class TestTimerCallbackException:
    async def test_timer_callback_exception_is_caught(self):
        """Timer catches exceptions from callback without re-raising."""
        timer = TurnTimer(TimerConfig(initial_bank_seconds=0.01))

        async def failing_callback():
            raise RuntimeError("callback failed")

        timer.start_turn_timer(failing_callback)
        # wait for timer to fire and handle the exception
        await asyncio.sleep(0.05)
        # timer should complete without raising
        assert timer._active_task is not None
        assert timer._active_task.done()
