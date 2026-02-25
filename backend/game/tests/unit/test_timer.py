import asyncio

from game.logic.timer import TimerConfig, TurnTimer


async def _noop() -> None:
    pass


class TestTurnTimerTurnTimer:
    async def test_turn_timer_callback_fires_on_timeout(self):
        config = TimerConfig(base_turn_seconds=0, initial_bank_seconds=0.05)
        timer = TurnTimer(config)
        callback_called = asyncio.Event()

        async def on_timeout():
            callback_called.set()

        timer.start_turn_timer(on_timeout)
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)
        assert callback_called.is_set()

    async def test_stop_deducts_elapsed_time(self):
        config = TimerConfig(base_turn_seconds=0, initial_bank_seconds=10.0)
        timer = TurnTimer(config)

        timer.start_turn_timer(_noop)
        await asyncio.sleep(0.1)
        timer.stop()

        # bank should be reduced by approximately 0.1 seconds
        assert timer._bank_seconds < 10.0
        assert timer._bank_seconds > 9.0

    async def test_stop_cancels_pending_timer(self):
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

        timer.start_meld_timer(_noop)
        await asyncio.sleep(0.05)
        timer.cancel()

        # bank time should not change for meld timers
        assert timer._bank_seconds == 10.0


class TestTurnTimerBankEdgeCases:
    async def test_bank_does_not_go_below_zero(self):
        config = TimerConfig(base_turn_seconds=0, initial_bank_seconds=0.05)
        timer = TurnTimer(config)

        timer.start_turn_timer(_noop)
        await asyncio.sleep(0.15)
        timer.stop()
        assert timer._bank_seconds == 0.0

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
        timer = TurnTimer(TimerConfig(base_turn_seconds=0, initial_bank_seconds=0.01))

        async def failing_callback():
            raise RuntimeError("callback failed")

        timer.start_turn_timer(failing_callback)
        # wait for timer to fire and handle the exception
        await asyncio.sleep(0.05)
        # timer should complete without raising
        assert timer._active_task is not None
        assert timer._active_task.done()


class TestBaseTimeBehavior:
    async def test_acting_within_base_time_does_not_drain_bank(self):
        """Player who acts within base time keeps their full bank."""
        config = TimerConfig(base_turn_seconds=1.0, initial_bank_seconds=10.0)
        timer = TurnTimer(config)
        timer.start_turn_timer(_noop)
        await asyncio.sleep(0.1)  # well within 1s base time
        timer.stop()
        assert timer.bank_seconds == 10.0

    async def test_acting_after_base_time_drains_only_excess(self):
        """Bank is only charged for time exceeding base time."""
        config = TimerConfig(base_turn_seconds=0.1, initial_bank_seconds=10.0)
        timer = TurnTimer(config)
        timer.start_turn_timer(_noop)
        await asyncio.sleep(0.2)  # ~0.1s over base time
        timer.stop()
        # should drain ~0.1s from bank; wide tolerance for CI scheduling jitter
        assert 9.5 < timer.bank_seconds < 10.0

    async def test_total_timer_is_base_plus_bank(self):
        """Timer fires after base + bank seconds."""
        config = TimerConfig(base_turn_seconds=0.05, initial_bank_seconds=0.05)
        timer = TurnTimer(config)
        callback_called = asyncio.Event()

        async def on_timeout():
            callback_called.set()

        timer.start_turn_timer(on_timeout)
        # should fire at ~0.1s (0.05 base + 0.05 bank)
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)


class TestBankCap:
    def test_round_bonus_capped_at_max_bank(self):
        """Bank doesn't grow beyond max_bank_seconds."""
        config = TimerConfig(
            initial_bank_seconds=55.0,
            max_bank_seconds=60.0,
            round_bonus_seconds=10.0,
        )
        timer = TurnTimer(config)
        timer.add_round_bonus()
        assert timer.bank_seconds == 60.0  # capped, not 65

    def test_round_bonus_below_cap(self):
        """Bank grows normally when below the cap."""
        config = TimerConfig(
            initial_bank_seconds=10.0,
            max_bank_seconds=60.0,
            round_bonus_seconds=10.0,
        )
        timer = TurnTimer(config)
        timer.add_round_bonus()
        assert timer.bank_seconds == 20.0
