"""Unit tests for TimerManager in isolation."""

import asyncio

import pytest

from game.logic.enums import TimeoutType
from game.logic.timer import TimerConfig
from game.session.models import Game, Player
from game.session.timer_manager import TimerManager
from game.tests.mocks import MockConnection


@pytest.fixture
def timeout_log():
    """Accumulator for timeout callbacks."""
    return []


@pytest.fixture
def timer_manager(timeout_log):
    async def on_timeout(game_id: str, timeout_type: TimeoutType, seat: int) -> None:
        timeout_log.append((game_id, timeout_type, seat))

    return TimerManager(on_timeout=on_timeout)


class TestTimerManagerCreate:
    def test_create_timers(self, timer_manager):
        """create_timers sets up timer instances for the given seats."""
        timer_manager.create_timers("g1", [0, 1, 2])
        assert timer_manager.has_game("g1")
        for seat in [0, 1, 2]:
            assert timer_manager.get_timer("g1", seat) is not None
        # seat 3 not created
        assert timer_manager.get_timer("g1", 3) is None

    def test_has_game_false_for_unknown_game(self, timer_manager):
        assert not timer_manager.has_game("unknown")

    def test_get_timer_returns_none_for_unknown_game(self, timer_manager):
        assert timer_manager.get_timer("unknown", 0) is None


class TestTimerManagerRemove:
    def test_remove_timer_returns_and_removes(self, timer_manager):
        timer_manager.create_timers("g1", [0, 1])
        timer = timer_manager.remove_timer("g1", 0)
        assert timer is not None
        # should be gone after removal
        assert timer_manager.get_timer("g1", 0) is None
        # other seats unaffected
        assert timer_manager.get_timer("g1", 1) is not None

    def test_remove_timer_returns_none_for_missing_seat(self, timer_manager):
        timer_manager.create_timers("g1", [0])
        assert timer_manager.remove_timer("g1", 5) is None

    def test_remove_timer_returns_none_for_missing_game(self, timer_manager):
        assert timer_manager.remove_timer("unknown", 0) is None


class TestTimerManagerCleanup:
    def test_cleanup_game_removes_all_timers(self, timer_manager):
        timer_manager.create_timers("g1", [0, 1, 2, 3])
        timer_manager.cleanup_game("g1")
        assert not timer_manager.has_game("g1")
        for seat in range(4):
            assert timer_manager.get_timer("g1", seat) is None

    async def test_cleanup_cancels_active_timers(self, timer_manager):
        timer_manager.create_timers("g1", [0])
        timer = timer_manager.get_timer("g1", 0)
        # start a turn timer to make it active
        timer_manager.start_turn_timer("g1", 0)
        assert timer._active_task is not None

        timer_manager.cleanup_game("g1")
        # task should be cancelled
        assert timer._active_task is None or timer._active_task.done()

    def test_cleanup_unknown_game_is_noop(self, timer_manager):
        # should not raise
        timer_manager.cleanup_game("unknown")


class TestTimerManagerStop:
    async def test_stop_player_timer(self, timer_manager):
        timer_manager.create_timers("g1", [0])
        timer = timer_manager.get_timer("g1", 0)
        timer_manager.start_turn_timer("g1", 0)
        assert timer._active_task is not None

        timer_manager.stop_player_timer("g1", 0)
        # timer task is cancelled and bank time deducted
        assert timer._active_task is None

    def test_stop_player_timer_noop_for_missing(self, timer_manager):
        # should not raise
        timer_manager.stop_player_timer("unknown", 0)


class TestTimerManagerCancel:
    async def test_cancel_other_timers(self, timer_manager):
        timer_manager.create_timers("g1", [0, 1, 2])
        # start meld timers for all seats
        for seat in [0, 1, 2]:
            timer_manager.start_meld_timer("g1", seat)

        timer_manager.cancel_other_timers("g1", exclude_seat=1)

        # seat 1's timer should still be active, others cancelled
        assert timer_manager.get_timer("g1", 0)._active_task is None
        assert timer_manager.get_timer("g1", 1)._active_task is not None
        assert timer_manager.get_timer("g1", 2)._active_task is None
        timer_manager.get_timer("g1", 1).cancel()

    def test_cancel_other_timers_noop_for_missing_game(self, timer_manager):
        # should not raise
        timer_manager.cancel_other_timers("unknown", exclude_seat=0)

    async def test_cancel_all(self, timer_manager):
        timer_manager.create_timers("g1", [0, 1])
        timer_manager.start_turn_timer("g1", 0)
        timer_manager.start_meld_timer("g1", 1)

        timer_manager.cancel_all("g1")

        # both timers cancelled but still registered
        assert timer_manager.has_game("g1")
        assert timer_manager.get_timer("g1", 0)._active_task is None
        assert timer_manager.get_timer("g1", 1)._active_task is None

    def test_cancel_all_noop_for_missing_game(self, timer_manager):
        # should not raise
        timer_manager.cancel_all("unknown")


class TestTimerManagerBank:
    async def test_consume_bank(self, timer_manager):
        timer_manager.create_timers("g1", [0])
        timer = timer_manager.get_timer("g1", 0)
        initial_bank = timer._bank_seconds

        # start a turn timer so bank time is being consumed
        timer_manager.start_turn_timer("g1", 0)
        # consume_bank deducts elapsed time without cancelling
        timer_manager.consume_bank("g1", 0)

        assert timer._bank_seconds <= initial_bank
        timer.cancel()

    def test_consume_bank_noop_for_missing(self, timer_manager):
        # should not raise
        timer_manager.consume_bank("unknown", 0)

    def test_add_round_bonus(self, timer_manager):
        timer_manager.create_timers("g1", [0, 1])
        timer0 = timer_manager.get_timer("g1", 0)
        timer1 = timer_manager.get_timer("g1", 1)
        initial0 = timer0._bank_seconds
        initial1 = timer1._bank_seconds

        timer_manager.add_round_bonus("g1")

        assert timer0._bank_seconds > initial0
        assert timer1._bank_seconds > initial1

    def test_add_round_bonus_noop_for_missing_game(self, timer_manager):
        # should not raise
        timer_manager.add_round_bonus("unknown")


class TestTimerManagerStartTurn:
    async def test_start_turn_timer(self, timer_manager):
        timer_manager.create_timers("g1", [0])
        timer = timer_manager.get_timer("g1", 0)

        timer_manager.start_turn_timer("g1", 0)
        assert timer._active_task is not None
        timer.cancel()

    def test_start_turn_timer_noop_for_missing_seat(self, timer_manager):
        timer_manager.create_timers("g1", [0])
        timer_manager.start_turn_timer("g1", 1)  # seat 1 doesn't exist -- should not raise

    async def test_turn_timer_fires_callback(self, timer_manager, timeout_log):
        """Turn timer timeout invokes the on_timeout callback with correct args."""
        config = TimerConfig(base_turn_seconds=0, initial_bank_seconds=0.01)
        timer_manager.create_timers("g1", [0], config=config)

        timer_manager.start_turn_timer("g1", 0)
        # wait for the timer to fire
        await asyncio.sleep(0.1)

        assert len(timeout_log) == 1
        assert timeout_log[0] == ("g1", TimeoutType.TURN, 0)


class TestTimerManagerStartMeld:
    async def test_start_meld_timer(self, timer_manager):
        timer_manager.create_timers("g1", [0])
        timer = timer_manager.get_timer("g1", 0)

        timer_manager.start_meld_timer("g1", 0)
        assert timer._active_task is not None
        timer.cancel()

    def test_start_meld_timer_noop_for_missing_seat(self, timer_manager):
        timer_manager.create_timers("g1", [0])
        timer_manager.start_meld_timer("g1", 2)  # seat 2 doesn't exist -- should not raise

    async def test_meld_timer_fires_callback(self, timer_manager, timeout_log):
        """Meld timer timeout invokes the on_timeout callback with MELD type."""
        timer_manager.create_timers("g1", [0])
        # meld timer uses fixed duration from config -- default is 2 seconds
        # override to be very short
        timer = timer_manager.get_timer("g1", 0)
        timer._config.meld_decision_seconds = 0.01

        timer_manager.start_meld_timer("g1", 0)
        await asyncio.sleep(0.1)

        assert len(timeout_log) == 1
        assert timeout_log[0] == ("g1", TimeoutType.MELD, 0)


class TestTimerManagerStartRoundAdvance:
    async def test_start_round_advance_timers(self, timer_manager):
        """start_round_advance_timers starts fixed-duration timers for each connected player."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        game = Game(game_id="g1")
        player1 = Player(connection=conn1, name="Alice", session_token="tok-alice", game_id="g1", seat=0)
        player2 = Player(connection=conn2, name="Bob", session_token="tok-bob", game_id="g1", seat=1)
        game.players[conn1.connection_id] = player1
        game.players[conn2.connection_id] = player2

        timer_manager.create_timers("g1", [0, 1])
        timer_manager.start_round_advance_timers(game)

        timer0 = timer_manager.get_timer("g1", 0)
        timer1 = timer_manager.get_timer("g1", 1)
        assert timer0._active_task is not None
        assert timer1._active_task is not None
        # fixed timer doesn't consume bank time
        assert timer0._turn_start_time is None
        assert timer1._turn_start_time is None
        timer0.cancel()
        timer1.cancel()

    def test_start_round_advance_timers_skips_unseated_players(self, timer_manager):
        """start_round_advance_timers skips players without a seat."""
        conn = MockConnection()
        game = Game(game_id="g1")
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="g1", seat=None)
        game.players[conn.connection_id] = player

        timer_manager.create_timers("g1", [0])
        timer_manager.start_round_advance_timers(game)
        # player has seat=None, so no timer at seat 0 should be started
        timer = timer_manager.get_timer("g1", 0)
        assert timer._active_task is None

    def test_start_round_advance_timers_noop_for_missing_game(self, timer_manager):
        """start_round_advance_timers does nothing if no timers exist for the game."""
        conn = MockConnection()
        game = Game(game_id="g1")
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="g1", seat=0)
        game.players[conn.connection_id] = player
        # no timers created
        timer_manager.start_round_advance_timers(game)

    async def test_round_advance_timer_fires_callback(self, timer_manager, timeout_log):
        """Round advance timer fires callback with ROUND_ADVANCE type."""
        conn = MockConnection()
        game = Game(game_id="g1")
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="g1", seat=0)
        game.players[conn.connection_id] = player

        timer_manager.create_timers("g1", [0])
        timer = timer_manager.get_timer("g1", 0)

        # directly start a fixed timer with short duration
        timer.start_fixed_timer(
            0.01,
            lambda: timer_manager._on_timeout("g1", TimeoutType.ROUND_ADVANCE, 0),
        )
        await asyncio.sleep(0.1)

        assert len(timeout_log) == 1
        assert timeout_log[0] == ("g1", TimeoutType.ROUND_ADVANCE, 0)
