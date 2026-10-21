import asyncio

import pytest

from game.logic.enums import TimeoutType
from game.logic.timer import TimerConfig
from game.session.models import Game, Player
from game.session.timer_manager import TimerManager
from game.tests.mocks import MockConnection


@pytest.fixture
def timeout_log():
    return []


@pytest.fixture
def timer_manager(timeout_log):
    async def on_timeout(game_id: str, timeout_type: TimeoutType, seat: int) -> None:
        timeout_log.append((game_id, timeout_type, seat))

    return TimerManager(on_timeout=on_timeout)


class TestTimerManagerCreate:
    def test_timer_manager__when_timers_created__should_register_only_given_seats(self, timer_manager):
        timer_manager.create_timers(game_id="g1", seats=[0, 1, 2])
        assert timer_manager.has_game("g1")
        for seat in [0, 1, 2]:
            assert timer_manager.get_timer("g1", seat) is not None
        # seat 3 not created
        assert timer_manager.get_timer("g1", 3) is None


class TestTimerManagerRemove:
    def test_timer_manager__when_removing_timer_of_unknown_game__should_return_none(self, timer_manager):
        assert timer_manager.remove_timer("unknown", 0) is None

    def test_timer_manager__when_timer_removed__should_return_it_and_keep_other_seats(self, timer_manager):
        timer_manager.create_timers(game_id="g1", seats=[0, 1])
        timer = timer_manager.remove_timer("g1", 0)
        assert timer is not None
        # should be gone after removal
        assert timer_manager.get_timer("g1", 0) is None
        # other seats unaffected
        assert timer_manager.get_timer("g1", 1) is not None


class TestTimerManagerCleanup:
    def test_timer_manager__when_game_cleaned_up__should_remove_all_timers(self, timer_manager):
        timer_manager.create_timers(game_id="g1", seats=[0, 1, 2, 3])
        timer_manager.cleanup_game("g1")
        assert not timer_manager.has_game("g1")
        for seat in range(4):
            assert timer_manager.get_timer("g1", seat) is None

    async def test_timer_manager__when_game_cleaned_up__should_cancel_active_timers(self, timer_manager):
        timer_manager.create_timers(game_id="g1", seats=[0])
        timer = timer_manager.get_timer("g1", 0)
        # start a turn timer to make it active
        timer_manager.start_turn_timer("g1", 0)
        active_task = timer._active_task
        assert active_task is not None

        timer_manager.cleanup_game("g1")
        await asyncio.sleep(0)
        assert active_task.cancelled()


class TestTimerManagerStop:
    async def test_timer_manager__when_player_timer_stopped__should_cancel_active_task(self, timer_manager):
        timer_manager.create_timers(game_id="g1", seats=[0])
        timer = timer_manager.get_timer("g1", 0)
        timer_manager.start_turn_timer("g1", 0)
        assert timer._active_task is not None

        timer_manager.stop_player_timer("g1", 0)
        # timer task is cancelled and bank time deducted
        assert timer._active_task is None


class TestTimerManagerCancel:
    async def test_timer_manager__when_cancelling_other_timers__should_keep_excluded_seat_active(self, timer_manager):
        timer_manager.create_timers(game_id="g1", seats=[0, 1, 2])
        # start meld timers for all seats
        for seat in [0, 1, 2]:
            timer_manager.start_meld_timer("g1", seat)

        timer_manager.cancel_other_timers("g1", exclude_seat=1)
        # seat 1's timer should still be active, others cancelled
        assert timer_manager.get_timer("g1", 0)._active_task is None
        assert timer_manager.get_timer("g1", 1)._active_task is not None
        assert timer_manager.get_timer("g1", 2)._active_task is None

        timer_manager.get_timer("g1", 1).cancel()

    async def test_timer_manager__when_cancel_all__should_cancel_tasks_and_keep_game_registered(self, timer_manager):
        timer_manager.create_timers(game_id="g1", seats=[0, 1])
        timer_manager.start_turn_timer("g1", 0)
        timer_manager.start_meld_timer("g1", 1)

        timer_manager.cancel_all("g1")
        # both timers cancelled but still registered
        assert timer_manager.has_game("g1")
        assert timer_manager.get_timer("g1", 0)._active_task is None
        assert timer_manager.get_timer("g1", 1)._active_task is None


class TestTimerManagerBank:
    async def test_timer_manager__when_bank_consumed__should_not_increase_bank_seconds(self, timer_manager):
        timer_manager.create_timers(game_id="g1", seats=[0])
        timer = timer_manager.get_timer("g1", 0)
        initial_bank = timer._bank_seconds

        # start a turn timer so bank time is being consumed
        timer_manager.start_turn_timer("g1", 0)
        # consume_bank deducts elapsed time without cancelling
        timer_manager.consume_bank("g1", 0)
        assert timer._bank_seconds <= initial_bank

        timer.cancel()

    def test_timer_manager__when_round_bonus_added__should_increase_every_seats_bank(self, timer_manager):
        timer_manager.create_timers(game_id="g1", seats=[0, 1])
        timer0 = timer_manager.get_timer("g1", 0)
        timer1 = timer_manager.get_timer("g1", 1)
        initial0 = timer0._bank_seconds
        initial1 = timer1._bank_seconds

        timer_manager.add_round_bonus("g1")
        assert timer0._bank_seconds > initial0
        assert timer1._bank_seconds > initial1


class TestTimerManagerStartTurn:
    async def test_timer_manager__when_turn_timer_started__should_have_active_task(self, timer_manager):
        timer_manager.create_timers(game_id="g1", seats=[0])
        timer = timer_manager.get_timer("g1", 0)

        timer_manager.start_turn_timer("g1", 0)
        assert timer._active_task is not None

        timer.cancel()

    async def test_timer_manager__when_turn_timer_expires__should_report_turn_timeout(self, timer_manager, timeout_log):
        config = TimerConfig(base_turn_seconds=0, initial_bank_seconds=0.01)
        timer_manager.create_timers(game_id="g1", seats=[0], config=config)

        timer_manager.start_turn_timer("g1", 0)
        # wait for the timer to fire
        await asyncio.sleep(0.1)
        assert len(timeout_log) == 1
        assert timeout_log[0] == ("g1", TimeoutType.TURN, 0)


class TestTimerManagerStartMeld:
    async def test_timer_manager__when_meld_timer_started__should_have_active_task(self, timer_manager):
        timer_manager.create_timers(game_id="g1", seats=[0])
        timer = timer_manager.get_timer("g1", 0)

        timer_manager.start_meld_timer("g1", 0)
        assert timer._active_task is not None

        timer.cancel()

    async def test_timer_manager__when_meld_timer_expires__should_report_meld_timeout(self, timer_manager, timeout_log):
        timer_manager.create_timers(game_id="g1", seats=[0])
        # meld timer uses fixed duration from config -- default is 2 seconds
        # override to be very short
        timer = timer_manager.get_timer("g1", 0)
        timer._config.meld_decision_seconds = 0.01

        timer_manager.start_meld_timer("g1", 0)
        await asyncio.sleep(0.1)
        assert len(timeout_log) == 1
        assert timeout_log[0] == ("g1", TimeoutType.MELD, 0)


class TestTimerManagerStartRoundAdvance:
    async def test_timer_manager__when_round_advance_timers_started__should_start_fixed_timers_for_seated_players(
        self, timer_manager
    ):
        conn1 = MockConnection()
        conn2 = MockConnection()
        game = Game(game_id="g1")
        player1 = Player(connection=conn1, name="Alice", session_token="tok-alice", game_id="g1", seat=0)
        player2 = Player(connection=conn2, name="Bob", session_token="tok-bob", game_id="g1", seat=1)
        game.players[conn1.connection_id] = player1
        game.players[conn2.connection_id] = player2

        timer_manager.create_timers(game_id="g1", seats=[0, 1])
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

    def test_timer_manager__when_player_unseated_at_round_advance__should_not_start_timer(self, timer_manager):
        conn = MockConnection()
        game = Game(game_id="g1")
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="g1", seat=None)
        game.players[conn.connection_id] = player

        timer_manager.create_timers(game_id="g1", seats=[0])
        timer_manager.start_round_advance_timers(game)
        # player has seat=None, so no timer at seat 0 should be started
        timer = timer_manager.get_timer("g1", 0)
        assert timer._active_task is None

    def test_timer_manager__when_round_advance_started_without_timers__should_not_raise(self, timer_manager):
        conn = MockConnection()
        game = Game(game_id="g1")
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="g1", seat=0)
        game.players[conn.connection_id] = player
        # no timers created
        timer_manager.start_round_advance_timers(game)

    async def test_timer_manager__when_round_advance_timer_expires__should_report_round_advance_timeout(
        self, timer_manager, timeout_log
    ):
        conn = MockConnection()
        game = Game(game_id="g1")
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="g1", seat=0)
        game.players[conn.connection_id] = player

        timer_manager.create_timers(game_id="g1", seats=[0])
        timer = timer_manager.get_timer("g1", 0)

        # directly start a fixed timer with short duration
        timer.start_fixed_timer(
            0.01,
            lambda: timer_manager._on_timeout("g1", TimeoutType.ROUND_ADVANCE, 0),
        )
        await asyncio.sleep(0.1)
        assert len(timeout_log) == 1
        assert timeout_log[0] == ("g1", TimeoutType.ROUND_ADVANCE, 0)
