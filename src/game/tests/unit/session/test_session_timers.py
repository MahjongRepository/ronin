import asyncio
from unittest.mock import AsyncMock

from game.logic.enums import CallType, GameAction, TimeoutType
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    DrawEvent,
    EventType,
    GameEndedEvent,
    RoundEndEvent,
    RoundStartedEvent,
    SeatTarget,
    ServiceEvent,
)
from game.logic.timer import TimerConfig, TurnTimer
from game.logic.types import (
    ExhaustiveDrawResult,
    GameEndResult,
    PlayerStanding,
    TenpaiHand,
)
from game.session.models import Game, Player
from game.tests.mocks import MockConnection, MockResultEvent

from .helpers import create_started_game, make_dummy_game_view, make_game_with_player


class TestSessionManagerTimers:
    async def test_game_cleanup_removes_timer_and_lock(self, manager):
        """Leaving a game cleans up timer and lock."""
        conns = await create_started_game(manager, "game1")

        assert manager._timer_manager.has_game("game1")
        assert "game1" in manager._game_locks

        await manager.leave_game(conns[0])
        assert not manager._timer_manager.has_game("game1")
        assert "game1" not in manager._game_locks

    async def test_turn_timeout_broadcasts_events(self, manager):
        """Turn timeout triggers handle_timeout and broadcasts result events."""
        conns = await create_started_game(manager, "game1")
        conns[0]._outbox.clear()

        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)

        timeout_msgs = [m for m in conns[0].sent_messages if m.get("type") == EventType.DRAW]
        assert len(timeout_msgs) == 1

    async def test_timeout_on_missing_game_does_nothing(self, manager):
        """Timeout on a non-existent game is silently ignored."""
        # should not raise
        await manager._handle_timeout("nonexistent", TimeoutType.TURN, seat=0)

    async def test_timeout_on_game_without_lock_does_nothing(self, manager):
        """Timeout when lock has been cleaned up is silently ignored."""
        conns = await create_started_game(manager, "game1")

        # remove lock to simulate cleanup race
        manager._game_locks.pop("game1", None)
        conns[0]._outbox.clear()

        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)

        # no events broadcast
        assert len(conns[0].sent_messages) == 0


class TestSessionManagerTimerIntegration:
    """Tests for timer integration methods."""

    def test_get_player_at_seat_returns_player(self, manager):
        """_get_player_at_seat returns the player at the specified seat."""
        game, _player, _conn = make_game_with_player(manager)

        result = manager._get_player_at_seat(game, 0)
        assert result is not None
        assert result.name == "Alice"
        assert result.seat == 0

    def test_get_player_at_seat_returns_none_for_unoccupied_seat(self, manager):
        """_get_player_at_seat returns None when no player is at the given seat."""
        game, _player, _conn = make_game_with_player(manager)

        result = manager._get_player_at_seat(game, 1)
        assert result is None

    def test_get_player_at_seat_returns_none_for_unseated_player(self, manager):
        """_get_player_at_seat returns None when no player has a seat assigned."""
        game = Game(game_id="game1")
        conn = MockConnection()
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="game1", seat=None)
        game.players[conn.connection_id] = player

        result = manager._get_player_at_seat(game, 0)
        assert result is None

    async def test_maybe_start_timer_with_draw_event(self, manager):
        """_maybe_start_timer starts a turn timer when DrawEvent targets the player."""
        game, _player, _conn = make_game_with_player(manager)
        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        draw_event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                target="seat_0",
                seat=0,
                available_actions=[],
            ),
            target=SeatTarget(seat=0),
        )

        await manager._maybe_start_timer(game, [draw_event])

        # timer should have an active task (turn timer started)
        assert timer._active_task is not None
        timer.cancel()

    async def test_maybe_start_timer_with_call_prompt_event(self, manager):
        """_maybe_start_timer starts a meld timer when per-seat CallPromptEvent targets the player."""
        game, _player, _conn = make_game_with_player(manager)
        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        call_event = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                type=EventType.CALL_PROMPT,
                target="all",
                call_type=CallType.MELD,
                tile_id=0,
                from_seat=1,
                callers=[0],
            ),
            target=SeatTarget(seat=0),
        )

        await manager._maybe_start_timer(game, [call_event])

        # timer should have an active task (meld timer started)
        assert timer._active_task is not None
        timer.cancel()

    async def test_maybe_start_timer_with_round_started_event(self, manager):
        """_maybe_start_timer adds round bonus to all player timers when RoundStartedEvent is present."""
        game, _player, _conn = make_game_with_player(manager)
        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer}
        initial_bank = timer.remaining_bank

        round_event = ServiceEvent(
            event=EventType.ROUND_STARTED,
            data=RoundStartedEvent(
                type=EventType.ROUND_STARTED,
                target="seat_0",
                view=make_dummy_game_view(),
            ),
            target=SeatTarget(seat=0),
        )

        await manager._maybe_start_timer(game, [round_event])

        config = TimerConfig()
        assert timer.remaining_bank == initial_bank + config.round_bonus_seconds

    async def test_maybe_start_timer_with_round_end_event(self, manager):
        """_maybe_start_timer starts fixed round-advance timers when RoundEndEvent is present."""
        game, _player, _conn = make_game_with_player(manager)
        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        round_end_event = ServiceEvent(
            event=EventType.ROUND_END,
            data=RoundEndEvent(
                type=EventType.ROUND_END,
                target="all",
                result=ExhaustiveDrawResult(
                    tempai_seats=[0],
                    noten_seats=[1, 2, 3],
                    tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
                    score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
                ),
            ),
            target=BroadcastTarget(),
        )

        await manager._maybe_start_timer(game, [round_end_event])

        # timer should have an active task (round advance timer started)
        assert timer._active_task is not None
        # fixed timer doesn't consume bank time
        assert timer._turn_start_time is None
        timer.cancel()

    async def test_maybe_start_timer_with_game_ended_event(self, manager):
        """_maybe_start_timer returns early and cleans up timers when GameEndedEvent is present."""
        game, _player, _conn = make_game_with_player(manager)
        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer}

        game_end_event = ServiceEvent(
            event=EventType.GAME_END,
            data=GameEndedEvent(
                type=EventType.GAME_END,
                target="all",
                result=GameEndResult(
                    winner_seat=0,
                    standings=[
                        PlayerStanding(seat=0, name="Alice", score=25000, final_score=0, is_ai_player=False),
                    ],
                ),
            ),
            target=BroadcastTarget(),
        )

        await manager._maybe_start_timer(game, [game_end_event])

        # timer task should not be started (game ended)
        assert timer._active_task is None

    async def test_maybe_start_timer_returns_when_timer_is_none(self, manager):
        """_maybe_start_timer returns early when no timer exists for the game."""
        game, _player, _conn = make_game_with_player(manager)
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
            target=BroadcastTarget(),
        )

        # should return without error
        await manager._maybe_start_timer(game, [generic_event])

    async def test_maybe_start_timer_no_connected_player_at_seat(self, manager):
        """_maybe_start_timer does not start timer when no connected player is at the target seat."""
        game = Game(game_id="game1")
        conn = MockConnection()
        # player at seat 1, but draw event targets seat 0 (no player there)
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="game1", seat=1)
        game.players[conn.connection_id] = player
        manager._games["game1"] = game

        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer, 1: TurnTimer()}

        draw_event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                target="seat_0",
                seat=0,
                available_actions=[],
            ),
            target=SeatTarget(seat=0),
        )

        await manager._maybe_start_timer(game, [draw_event])
        assert timer._active_task is None

    async def test_handle_timeout_returns_when_game_is_none(self, manager):
        """_handle_timeout returns early when game has been removed but lock still exists."""
        _game, _player, _conn = make_game_with_player(manager)
        manager._game_locks["game1"] = asyncio.Lock()

        # remove the game to simulate the game being cleaned up
        manager._games.pop("game1", None)

        # should return without error
        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)

    async def test_handle_timeout_returns_when_no_player_at_seat(self, manager):
        """_handle_timeout returns early when no player is at the timed-out seat."""
        game = Game(game_id="game1")
        conn = MockConnection()
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="game1", seat=1)
        game.players[conn.connection_id] = player
        manager._games["game1"] = game
        manager._game_locks["game1"] = asyncio.Lock()

        # seat 0 has no player
        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)
        assert len(conn.sent_messages) == 0


class TestPerPlayerTimers:
    """Tests for per-player timer independence."""

    def _make_pvp_game_with_two_players(
        self, manager
    ) -> tuple[Game, Player, Player, MockConnection, MockConnection]:
        """Create a game with two players at seats 0 and 1."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        game = Game(game_id="game1")
        player1 = Player(connection=conn1, name="Alice", session_token="tok-alice", game_id="game1", seat=0)
        player2 = Player(connection=conn2, name="Bob", session_token="tok-bob", game_id="game1", seat=1)
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
        await create_started_game(manager, "game1", num_ai_players=0, player_names=["P0", "P1", "P2", "P3"])

        for seat in range(4):
            timer = manager._timer_manager.get_timer("game1", seat)
            assert timer is not None
            assert isinstance(timer, TurnTimer)

    async def test_round_bonus_added_to_all_player_timers(self, manager):
        """Round bonus is added to all player timers when round starts."""
        game, _p1, _p2, _c1, _c2 = self._make_pvp_game_with_two_players(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer0, 1: timer1}
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
            target=SeatTarget(seat=0),
        )

        await manager._maybe_start_timer(game, [round_event])

        config = TimerConfig()
        assert timer0.remaining_bank == initial_bank_0 + config.round_bonus_seconds
        assert timer1.remaining_bank == initial_bank_1 + config.round_bonus_seconds

    async def test_multiple_meld_timers_for_multiple_callers(self, manager):
        """When 2+ players can call the same discard, each gets their own meld timer."""
        game, _p1, _p2, _c1, _c2 = self._make_pvp_game_with_two_players(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        call_events = [
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[0],
                ),
                target=SeatTarget(seat=0),
            ),
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[1],
                ),
                target=SeatTarget(seat=1),
            ),
        ]

        await manager._maybe_start_timer(game, call_events)

        # both timers should have active tasks (meld timer started for each)
        assert timer0._active_task is not None
        assert timer1._active_task is not None
        timer0.cancel()
        timer1.cancel()

    async def test_sibling_meld_timer_cancellation(self, manager):
        """When one caller acts, other callers' meld timers are cancelled."""
        game, _p1, _p2, conn1, _c2 = self._make_pvp_game_with_two_players(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        call_events = [
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[0],
                ),
                target=SeatTarget(seat=0),
            ),
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[1],
                ),
                target=SeatTarget(seat=1),
            ),
        ]
        await manager._maybe_start_timer(game, call_events)
        assert timer0._active_task is not None
        assert timer1._active_task is not None

        # player at seat 0 acts (handle_game_action)
        conn1._outbox.clear()
        await manager.handle_game_action(conn1, GameAction.DISCARD, {})

        # seat 0's timer should be stopped (bank time deducted), seat 1's cancelled
        assert timer1._active_task is None

    async def test_partial_pass_stops_acting_player_timer(self, manager):
        """When a pass returns empty events (other callers pending), the passer's timer is stopped."""
        game, _p1, _p2, conn1, _c2 = self._make_pvp_game_with_two_players(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        call_events = [
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[0],
                ),
                target=SeatTarget(seat=0),
            ),
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[1],
                ),
                target=SeatTarget(seat=1),
            ),
        ]
        await manager._maybe_start_timer(game, call_events)
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
        game, _p1, _p2, _c1, _c2 = self._make_pvp_game_with_two_players(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        draw_event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                target="seat_0",
                seat=0,
                available_actions=[],
            ),
            target=SeatTarget(seat=0),
        )

        await manager._maybe_start_timer(game, [draw_event])

        # only seat 0's timer should be active
        assert timer0._active_task is not None
        assert timer1._active_task is None
        timer0.cancel()

    async def test_leave_game_cancels_all_player_timers(self, manager):
        """Leaving a game cancels all player timers when game becomes empty."""
        conns = await create_started_game(
            manager,
            "game1",
            num_ai_players=0,
            player_names=["P0", "P1", "P2", "P3"],
        )

        assert manager._timer_manager.has_game("game1")

        # all players leave
        for c in conns:
            await manager.leave_game(c)

        assert not manager._timer_manager.has_game("game1")
