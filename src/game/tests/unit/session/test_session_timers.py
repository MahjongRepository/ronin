import asyncio
from unittest.mock import AsyncMock

from game.logic.enums import CallType, GameAction, MeldCallType, TimeoutType
from game.logic.timer import TimerConfig, TurnTimer
from game.logic.types import (
    ExhaustiveDrawResult,
    GameEndResult,
    MeldCaller,
    PlayerStanding,
)
from game.messaging.events import (
    CallPromptEvent,
    EventType,
    GameEndedEvent,
    RoundEndEvent,
    RoundStartedEvent,
    ServiceEvent,
    TurnEvent,
)
from game.session.models import Game, Player
from game.tests.mocks import MockConnection, MockResultEvent

from .helpers import make_dummy_game_view, make_game_with_human


class TestSessionManagerTimers:
    async def test_game_cleanup_removes_timer_and_lock(self, manager):
        """Leaving a game cleans up timer and lock."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")
        assert "game1" in manager._timers
        assert "game1" in manager._game_locks

        await manager.leave_game(conn)
        assert "game1" not in manager._timers
        assert "game1" not in manager._game_locks

    async def test_turn_timeout_broadcasts_events(self, manager):
        """Turn timeout triggers handle_timeout and broadcasts result events."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)

        timeout_msgs = [m for m in conn.sent_messages if m.get("type") == EventType.DRAW]
        assert len(timeout_msgs) == 1

    async def test_timeout_on_missing_game_does_nothing(self, manager):
        """Timeout on a non-existent game is silently ignored."""
        # should not raise
        await manager._handle_timeout("nonexistent", TimeoutType.TURN, seat=0)

    async def test_timeout_on_game_without_lock_does_nothing(self, manager):
        """Timeout when lock has been cleaned up is silently ignored."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")

        # remove lock to simulate cleanup race
        manager._game_locks.pop("game1", None)
        conn._outbox.clear()

        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)

        # no events broadcast
        assert len(conn.sent_messages) == 0


class TestSessionManagerTimerIntegration:
    """Tests for timer integration methods."""

    def test_get_player_at_seat_returns_player(self, manager):
        """_get_player_at_seat returns the player at the specified seat."""
        game, _player, _conn = make_game_with_human(manager)

        result = manager._get_player_at_seat(game, 0)
        assert result is not None
        assert result.name == "Alice"
        assert result.seat == 0

    def test_get_player_at_seat_returns_none_for_unoccupied_seat(self, manager):
        """_get_player_at_seat returns None when no player is at the given seat."""
        game, _player, _conn = make_game_with_human(manager)

        result = manager._get_player_at_seat(game, 1)
        assert result is None

    def test_get_player_at_seat_returns_none_for_unseated_player(self, manager):
        """_get_player_at_seat returns None when no player has a seat assigned."""
        game = Game(game_id="game1")
        conn = MockConnection()
        player = Player(connection=conn, name="Alice", game_id="game1", seat=None)
        game.players[conn.connection_id] = player

        result = manager._get_player_at_seat(game, 0)
        assert result is None

    def test_get_caller_seats_deduplicates_meld_callers(self, manager):
        """_get_caller_seats returns unique seats when same player has multiple meld options."""
        callers = [
            MeldCaller(seat=0, call_type=MeldCallType.PON),
            MeldCaller(seat=0, call_type=MeldCallType.CHI, options=((57, 63),)),
        ]
        assert manager._get_caller_seats(callers) == [0]

    def test_cleanup_timer_on_game_end_cancels_timer(self, manager):
        """_cleanup_timer_on_game_end cancels all player timers when GameEndedEvent is present."""
        game, _player, _conn = make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}

        game_end_event = ServiceEvent(
            event=EventType.GAME_END,
            data=GameEndedEvent(
                type=EventType.GAME_END,
                target="all",
                result=GameEndResult(
                    winner_seat=0,
                    standings=[
                        PlayerStanding(seat=0, name="Alice", score=25000, final_score=0, is_bot=False),
                    ],
                ),
            ),
            target="all",
        )

        result = manager._cleanup_timer_on_game_end(game, [game_end_event])
        assert result is True

    def test_cleanup_timer_on_game_end_returns_false_without_end_event(self, manager):
        """_cleanup_timer_on_game_end returns False when no GameEndedEvent is present."""
        game, _player, _conn = make_game_with_human(manager)

        generic_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                player="Alice",
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target="all",
        )

        result = manager._cleanup_timer_on_game_end(game, [generic_event])
        assert result is False

    async def test_maybe_start_timer_with_turn_event(self, manager):
        """_maybe_start_timer starts a turn timer when TurnEvent targets the human player."""
        game, _player, _conn = make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        turn_event = ServiceEvent(
            event=EventType.TURN,
            data=TurnEvent(
                type=EventType.TURN,
                target="seat_0",
                current_seat=0,
                available_actions=[],
                wall_count=70,
            ),
            target="seat_0",
        )

        await manager._maybe_start_timer(game, [turn_event])

        # timer should have an active task (turn timer started)
        assert timer._active_task is not None
        timer.cancel()

    async def test_maybe_start_timer_with_call_prompt_event(self, manager):
        """_maybe_start_timer starts a meld timer when CallPromptEvent targets the human player."""
        game, _player, _conn = make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        call_event = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                type=EventType.CALL_PROMPT,
                target="seat_0",
                call_type=CallType.MELD,
                tile_id=0,
                from_seat=1,
                callers=[0],
            ),
            target="seat_0",
        )

        await manager._maybe_start_timer(game, [call_event])

        # timer should have an active task (meld timer started)
        assert timer._active_task is not None
        timer.cancel()

    async def test_maybe_start_timer_with_round_started_event(self, manager):
        """_maybe_start_timer adds round bonus to all player timers when RoundStartedEvent is present."""
        game, _player, _conn = make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}
        initial_bank = timer.remaining_bank

        round_event = ServiceEvent(
            event=EventType.ROUND_STARTED,
            data=RoundStartedEvent(
                type=EventType.ROUND_STARTED,
                target="seat_0",
                view=make_dummy_game_view(),
            ),
            target="seat_0",
        )

        await manager._maybe_start_timer(game, [round_event])

        config = TimerConfig()
        assert timer.remaining_bank == initial_bank + config.round_bonus_seconds

    async def test_maybe_start_timer_with_round_end_event(self, manager):
        """_maybe_start_timer starts fixed round-advance timers when RoundEndEvent is present."""
        game, _player, _conn = make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        round_end_event = ServiceEvent(
            event=EventType.ROUND_END,
            data=RoundEndEvent(
                type=EventType.ROUND_END,
                target="all",
                result=ExhaustiveDrawResult(
                    tempai_seats=[0],
                    noten_seats=[1, 2, 3],
                    score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
                ),
            ),
            target="all",
        )

        await manager._maybe_start_timer(game, [round_end_event])

        # timer should have an active task (round advance timer started)
        assert timer._active_task is not None
        # fixed timer doesn't consume bank time
        assert timer._turn_start_time is None
        timer.cancel()

    async def test_maybe_start_timer_with_game_ended_event(self, manager):
        """_maybe_start_timer returns early and cleans up timers when GameEndedEvent is present."""
        game, _player, _conn = make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}

        game_end_event = ServiceEvent(
            event=EventType.GAME_END,
            data=GameEndedEvent(
                type=EventType.GAME_END,
                target="all",
                result=GameEndResult(
                    winner_seat=0,
                    standings=[
                        PlayerStanding(seat=0, name="Alice", score=25000, final_score=0, is_bot=False),
                    ],
                ),
            ),
            target="all",
        )

        await manager._maybe_start_timer(game, [game_end_event])

        # timer task should not be started (game ended)
        assert timer._active_task is None

    async def test_maybe_start_timer_returns_when_timer_is_none(self, manager):
        """_maybe_start_timer returns early when no timer exists for the game."""
        game, _player, _conn = make_game_with_human(manager)
        # do not set up a timer for the game

        generic_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                player="Alice",
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target="all",
        )

        # should return without error
        await manager._maybe_start_timer(game, [generic_event])

    async def test_maybe_start_timer_no_connected_player_at_seat(self, manager):
        """_maybe_start_timer does not start timer when no connected player is at the target seat."""
        game = Game(game_id="game1")
        conn = MockConnection()
        # player at seat 1, but turn event targets seat 0 (no player there)
        player = Player(connection=conn, name="Alice", game_id="game1", seat=1)
        game.players[conn.connection_id] = player
        manager._games["game1"] = game

        timer = TurnTimer()
        manager._timers["game1"] = {0: timer, 1: TurnTimer()}

        turn_event = ServiceEvent(
            event=EventType.TURN,
            data=TurnEvent(
                type=EventType.TURN,
                target="seat_0",
                current_seat=0,
                available_actions=[],
                wall_count=70,
            ),
            target="seat_0",
        )

        await manager._maybe_start_timer(game, [turn_event])
        assert timer._active_task is None

    async def test_handle_timeout_returns_when_game_is_none(self, manager):
        """_handle_timeout returns early when game has been removed but lock still exists."""
        _game, _player, _conn = make_game_with_human(manager)
        manager._game_locks["game1"] = asyncio.Lock()

        # remove the game to simulate the game being cleaned up
        manager._games.pop("game1", None)

        # should return without error
        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)

    async def test_handle_timeout_returns_when_no_player_at_seat(self, manager):
        """_handle_timeout returns early when no player is at the timed-out seat."""
        game = Game(game_id="game1")
        conn = MockConnection()
        player = Player(connection=conn, name="Alice", game_id="game1", seat=1)
        game.players[conn.connection_id] = player
        manager._games["game1"] = game
        manager._game_locks["game1"] = asyncio.Lock()

        # seat 0 has no player
        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)
        assert len(conn.sent_messages) == 0


class TestPerPlayerTimers:
    """Tests for per-player timer independence."""

    def _make_pvp_game_with_two_humans(
        self, manager
    ) -> tuple[Game, Player, Player, MockConnection, MockConnection]:
        """Create a game with two human players at seats 0 and 1."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        game = Game(game_id="game1")
        player1 = Player(connection=conn1, name="Alice", game_id="game1", seat=0)
        player2 = Player(connection=conn2, name="Bob", game_id="game1", seat=1)
        game.players[conn1.connection_id] = player1
        game.players[conn2.connection_id] = player2
        manager._games["game1"] = game
        manager._players[conn1.connection_id] = player1
        manager._players[conn2.connection_id] = player2
        manager._connections[conn1.connection_id] = conn1
        manager._connections[conn2.connection_id] = conn2
        return game, player1, player2, conn1, conn2

    async def test_pvp_game_creates_timer_per_player(self, manager):
        """PVP game with 4 players creates a timer for each player."""
        conns = [MockConnection() for _ in range(4)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        timers = manager._timers["game1"]
        assert len(timers) == 4
        for seat in range(4):
            assert seat in timers
            assert isinstance(timers[seat], TurnTimer)

    async def test_round_bonus_added_to_all_player_timers(self, manager):
        """Round bonus is added to all player timers when round starts."""
        game, _p1, _p2, _c1, _c2 = self._make_pvp_game_with_two_humans(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        initial_bank_0 = timer0.remaining_bank
        initial_bank_1 = timer1.remaining_bank

        round_event = ServiceEvent(
            event=EventType.ROUND_STARTED,
            data=RoundStartedEvent(
                type=EventType.ROUND_STARTED,
                target="seat_0",
                view=make_dummy_game_view(),
            ),
            target="seat_0",
        )

        await manager._maybe_start_timer(game, [round_event])

        config = TimerConfig()
        assert timer0.remaining_bank == initial_bank_0 + config.round_bonus_seconds
        assert timer1.remaining_bank == initial_bank_1 + config.round_bonus_seconds

    async def test_multiple_meld_timers_for_multiple_callers(self, manager):
        """When 2+ humans can call the same discard, each gets their own meld timer."""
        game, _p1, _p2, _c1, _c2 = self._make_pvp_game_with_two_humans(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        # both seat 0 and seat 1 can call
        call_event = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                type=EventType.CALL_PROMPT,
                target="all",
                call_type=CallType.MELD,
                tile_id=42,
                from_seat=2,
                callers=[0, 1],
            ),
            target="all",
        )

        await manager._maybe_start_timer(game, [call_event])

        # both timers should have active tasks (meld timer started for each)
        assert timer0._active_task is not None
        assert timer1._active_task is not None
        timer0.cancel()
        timer1.cancel()

    async def test_sibling_meld_timer_cancellation(self, manager):
        """When one caller acts, other callers' meld timers are cancelled."""
        game, _p1, _p2, conn1, _c2 = self._make_pvp_game_with_two_humans(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        # start meld timers for both callers
        call_event = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                type=EventType.CALL_PROMPT,
                target="all",
                call_type=CallType.MELD,
                tile_id=42,
                from_seat=2,
                callers=[0, 1],
            ),
            target="all",
        )
        await manager._maybe_start_timer(game, [call_event])
        assert timer0._active_task is not None
        assert timer1._active_task is not None

        # player at seat 0 acts (handle_game_action)
        conn1._outbox.clear()
        await manager.handle_game_action(conn1, GameAction.DISCARD, {})

        # seat 0's timer should be stopped (bank time deducted), seat 1's cancelled
        assert timer1._active_task is None

    async def test_partial_pass_stops_acting_player_timer(self, manager):
        """When a pass returns empty events (other callers pending), the passer's timer is stopped."""
        game, _p1, _p2, conn1, _c2 = self._make_pvp_game_with_two_humans(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        # start meld timers for both callers
        call_event = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                type=EventType.CALL_PROMPT,
                target="all",
                call_type=CallType.MELD,
                tile_id=42,
                from_seat=2,
                callers=[0, 1],
            ),
            target="all",
        )
        await manager._maybe_start_timer(game, [call_event])
        assert timer0._active_task is not None
        assert timer1._active_task is not None

        # mock returns empty events (partial pass, other callers still pending)
        manager._game_service.handle_action = AsyncMock(return_value=[])
        conn1._outbox.clear()
        await manager.handle_game_action(conn1, GameAction.PASS, {})

        # seat 0's timer should be stopped, seat 1's timer should still be running
        assert timer0._active_task is None
        assert timer1._active_task is not None
        timer1.cancel()

    async def test_turn_timer_starts_for_specific_player(self, manager):
        """Turn timer starts only for the player whose turn it is."""
        game, _p1, _p2, _c1, _c2 = self._make_pvp_game_with_two_humans(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        turn_event = ServiceEvent(
            event=EventType.TURN,
            data=TurnEvent(
                type=EventType.TURN,
                target="seat_0",
                current_seat=0,
                available_actions=[],
                wall_count=70,
            ),
            target="seat_0",
        )

        await manager._maybe_start_timer(game, [turn_event])

        # only seat 0's timer should be active
        assert timer0._active_task is not None
        assert timer1._active_task is None
        timer0.cancel()

    async def test_leave_game_cancels_all_player_timers(self, manager):
        """Leaving a game cancels all player timers when game becomes empty."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=0)

        # join 4 players to start the game
        conns = [conn1, conn2, MockConnection(), MockConnection()]
        for c in conns[2:]:
            manager.register_connection(c)
        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        assert "game1" in manager._timers

        # all players leave
        for c in conns:
            await manager.leave_game(c)

        assert "game1" not in manager._timers
