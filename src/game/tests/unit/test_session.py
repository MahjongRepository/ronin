import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, patch

import pytest

from game.logic.enums import CallType, MeldCallType, TimeoutType
from game.logic.timer import TimerConfig, TurnTimer
from game.logic.types import (
    ExhaustiveDrawResult,
    GameEndResult,
    GameView,
    MeldCaller,
    PlayerStanding,
    PlayerView,
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
from game.messaging.types import SessionMessageType
from game.session.manager import HEARTBEAT_TIMEOUT, SessionManager
from game.session.models import Game, Player
from game.tests.mocks import MockConnection, MockGameService, MockResultEvent


def _make_dummy_game_view() -> GameView:
    """Create a minimal GameView for testing."""
    return GameView(
        seat=0,
        round_wind="East",
        round_number=1,
        dealer_seat=0,
        current_player_seat=0,
        wall_count=70,
        dora_indicators=[],
        honba_sticks=0,
        riichi_sticks=0,
        players=[
            PlayerView(
                seat=0,
                name="Alice",
                is_bot=False,
                score=25000,
                is_riichi=False,
                discards=[],
                melds=[],
                tile_count=13,
            ),
        ],
        phase="playing",
        game_phase="east",
    )


class TestSessionManager:
    @pytest.fixture
    def manager(self):
        game_service = MockGameService()
        return SessionManager(game_service)

    async def test_join_game_adds_player(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        game = manager.get_game("game1")
        assert game is not None
        assert game.player_count == 1
        assert "Alice" in game.player_names

    async def test_join_game_notifies_player(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        # first message is game_joined, then game_started event from start_game
        assert len(conn.sent_messages) >= 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.GAME_JOINED

    async def test_join_game_starts_game_on_first_player(self, manager):
        """When first player joins, start_game is called and game_started events are sent."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        # should receive: game_joined + game_started (broadcast) + round_started (seat_0)
        game_started_events = [m for m in conn.sent_messages if m.get("type") == "game_started"]
        assert len(game_started_events) == 1

    async def test_second_player_notifies_first(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        # conn1 should have received: game_joined + player_joined + game_started
        player_joined_msgs = [
            m for m in conn1.sent_messages if m.get("type") == SessionMessageType.PLAYER_JOINED
        ]
        assert len(player_joined_msgs) == 1
        assert player_joined_msgs[0]["player_name"] == "Bob"

    async def test_leave_game_notifies_others(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        # clear previous messages
        conn1._outbox.clear()

        await manager.leave_game(conn2)

        assert len(conn1.sent_messages) == 1
        assert conn1.sent_messages[0]["type"] == SessionMessageType.PLAYER_LEFT
        assert conn1.sent_messages[0]["player_name"] == "Bob"

    async def test_join_started_game_error(self, manager):
        connections = [MockConnection() for _ in range(5)]
        for conn in connections:
            manager.register_connection(conn)
        manager.create_game("game1", num_bots=0)

        # join 4 players, game starts automatically
        for i, conn in enumerate(connections[:4]):
            await manager.join_game(conn, "game1", f"Player{i}")

        # 5th player should get error since game already started
        await manager.join_game(connections[4], "game1", "Player4")

        msg = connections[4].sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == "game_started"

    async def test_game_full_error(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        conn3 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.register_connection(conn3)
        # num_bots=2 means only 2 humans needed
        manager.create_game("game1", num_bots=2)

        game = manager.get_game("game1")
        # directly inject 2 players to fill capacity without triggering start
        game.players["fake1"] = Player(connection=conn1, name="Fake1", game_id="game1")
        game.players["fake2"] = Player(connection=conn2, name="Fake2", game_id="game1")

        # 3rd player gets game_full (game hasn't started, but at capacity)
        await manager.join_game(conn3, "game1", "Player2")

        msg = conn3.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == "game_full"

    async def test_duplicate_name_error(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Alice")

        msg = conn2.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == "name_taken"

    async def test_empty_game_is_cleaned_up(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")
        assert manager.get_game("game1") is not None

        await manager.leave_game(conn)
        assert manager.get_game("game1") is None

    async def test_join_nonexistent_game_returns_error(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_game(conn, "nonexistent", "Alice")

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == "game_not_found"

    async def test_handle_game_action_broadcasts_events(self, manager):
        """handle_game_action processes list of events and broadcasts them."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        await manager.handle_game_action(conn, "test_action", {"key": "value"})

        # mock service returns one event with target "all"
        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == "test_action_result"

    async def test_targeted_events_only_sent_to_target_player(self, manager):
        """Events with seat_N target go only to the player at that seat."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        # manually broadcast a seat-targeted event
        game = manager.get_game("game1")
        seat_event = ServiceEvent(
            event="turn",
            data=TurnEvent(
                current_seat=0,
                available_actions=[],
                wall_count=70,
                target="seat_0",
            ),
            target="seat_0",
        )
        await manager._broadcast_events(game, [seat_event])

        # only conn1 (seat 0) should receive the event
        assert len(conn1.sent_messages) == 1
        assert len(conn2.sent_messages) == 0

    async def test_broadcast_events_sends_all_target_to_everyone(self, manager):
        """Events with 'all' target are broadcast to all players."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        # perform action that generates broadcast event
        await manager.handle_game_action(conn1, "test_action", {})

        # both players should receive the event
        assert len(conn1.sent_messages) == 1
        assert len(conn2.sent_messages) == 1
        assert conn1.sent_messages[0]["type"] == "test_action_result"
        assert conn2.sent_messages[0]["type"] == "test_action_result"

    async def test_call_prompt_only_sent_to_callers(self, manager):
        """CallPromptEvent is only sent to seats listed in callers, not to all players."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        # manually broadcast a call_prompt targeting only seat 0 (Alice)
        game = manager.get_game("game1")
        call_event = ServiceEvent(
            event="call_prompt",
            data=CallPromptEvent(
                call_type=CallType.RON,
                tile_id=42,
                from_seat=2,
                callers=[0],
                target="all",
            ),
            target="all",
        )
        await manager._broadcast_events(game, [call_event])

        # only conn1 (seat 0) should receive the call_prompt
        assert len(conn1.sent_messages) == 1
        assert conn1.sent_messages[0]["type"] == "call_prompt"
        assert len(conn2.sent_messages) == 0

    async def test_call_prompt_sent_once_when_player_has_multiple_meld_options(self, manager):
        """CallPromptEvent is sent once per player even when they have both pon and chi options."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        # seat 0 can both pon and chi the same tile — two MeldCaller entries for the same seat
        game = manager.get_game("game1")
        callers = [
            MeldCaller(seat=0, call_type=MeldCallType.PON),
            MeldCaller(seat=0, call_type=MeldCallType.CHI, options=[(57, 63)]),
        ]
        call_event = ServiceEvent(
            event="call_prompt",
            data=CallPromptEvent(
                call_type=CallType.MELD,
                tile_id=55,
                from_seat=3,
                callers=callers,
                target="all",
            ),
            target="all",
        )
        await manager._broadcast_events(game, [call_event])

        # seat 0 should receive the call_prompt exactly once
        assert len(conn1.sent_messages) == 1
        assert conn1.sent_messages[0]["type"] == "call_prompt"
        # seat 1 (Bob) should not receive it
        assert len(conn2.sent_messages) == 0

    async def test_start_game_not_called_on_second_player(self, manager):
        """start_game is called once when both players join, not again on subsequent actions."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")

        # game should not have started yet (needs 2 humans)
        game = manager.get_game("game1")
        assert game.started is False

        await manager.join_game(conn2, "game1", "Bob")

        # game starts on second join
        assert game.started is True

        # each connection should have exactly one game_started event
        for c in [conn1, conn2]:
            game_started_events = [m for m in c.sent_messages if m.get("type") == "game_started"]
            assert len(game_started_events) == 1


class TestSessionManagerTimers:
    @pytest.fixture
    def manager(self):
        game_service = MockGameService()
        return SessionManager(game_service)

    async def test_timer_created_on_game_start(self, manager):
        """Per-player timer dict is created when a game starts."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        assert "game1" in manager._timers
        assert isinstance(manager._timers["game1"], dict)
        # seat 0 should have a timer (Alice is at seat 0 in mock service)
        assert 0 in manager._timers["game1"]
        assert isinstance(manager._timers["game1"][0], TurnTimer)

    async def test_lock_created_on_game_start(self, manager):
        """Asyncio lock is created when a game starts."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        assert "game1" in manager._game_locks

    async def test_timer_gets_initial_round_bonus(self, manager):
        """Player timer receives the first round bonus on game start."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        timer = manager._timers["game1"][0]
        config = TimerConfig()
        assert timer.remaining_bank == config.initial_bank_seconds + config.round_bonus_seconds

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

        # mock service returns a timeout_turn event with target "all"
        timeout_msgs = [m for m in conn.sent_messages if m.get("type") == "timeout_turn"]
        assert len(timeout_msgs) == 1

    async def test_meld_timeout_broadcasts_events(self, manager):
        """Meld timeout triggers handle_timeout and broadcasts result events."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        await manager._handle_timeout("game1", TimeoutType.MELD, seat=0)

        timeout_msgs = [m for m in conn.sent_messages if m.get("type") == "timeout_meld"]
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


class TestSessionManagerDefensiveChecks:
    """Tests for defensive checks that guard against invalid state."""

    @pytest.fixture
    def manager(self):
        game_service = MockGameService()
        return SessionManager(game_service)

    async def test_get_player_returns_player(self, manager):
        """get_player returns the player after joining a game."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        player = manager.get_player(conn)
        assert player is not None
        assert player.name == "Alice"

    async def test_get_player_returns_none_for_unknown(self, manager):
        """get_player returns None for a connection that has not joined a game."""
        conn = MockConnection()
        manager.register_connection(conn)

        player = manager.get_player(conn)
        assert player is None

    async def test_join_game_already_in_game_returns_error(self, manager):
        """Joining a second game while already in one returns an error."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        manager.create_game("game2")

        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        await manager.join_game(conn, "game2", "Alice")

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == "already_in_game"

    async def test_leave_game_when_game_is_none(self, manager):
        """Leaving when the game mapping is missing does not raise."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        # remove the game from the internal mapping to simulate the defensive case
        player = manager._players[conn.connection_id]
        manager._games.pop(player.game_id, None)

        # should return without error
        await manager.leave_game(conn)

    async def test_handle_game_action_not_in_game_returns_error(self, manager):
        """Performing a game action without joining returns an error."""
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.handle_game_action(conn, "test_action", {})

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == "not_in_game"

    async def test_handle_game_action_game_is_none(self, manager):
        """Performing a game action when game is missing from mapping does not raise."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        # remove the game from the internal mapping
        manager._games.pop("game1", None)

        # should return silently without error
        await manager.handle_game_action(conn, "test_action", {})
        assert len(conn.sent_messages) == 0

    async def test_broadcast_chat_game_is_none(self, manager):
        """Broadcasting chat when game is missing from mapping does not raise."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        # remove the game from the internal mapping
        manager._games.pop("game1", None)

        # should return silently without error
        await manager.broadcast_chat(conn, "hello")
        assert len(conn.sent_messages) == 0


class TestSessionManagerTimerIntegration:
    """Tests for timer integration methods."""

    @pytest.fixture
    def manager(self):
        game_service = MockGameService()
        return SessionManager(game_service)

    def _make_game_with_human(self, manager) -> tuple[Game, Player, MockConnection]:
        """Create a game with a human player who has an assigned seat."""
        conn = MockConnection()
        game = Game(game_id="game1")
        player = Player(connection=conn, name="Alice", game_id="game1", seat=0)
        game.players[conn.connection_id] = player
        manager._games["game1"] = game
        manager._players[conn.connection_id] = player
        manager._connections[conn.connection_id] = conn
        return game, player, conn

    def test_get_player_at_seat_returns_player(self, manager):
        """_get_player_at_seat returns the player at the specified seat."""
        game, _player, _conn = self._make_game_with_human(manager)

        result = manager._get_player_at_seat(game, 0)
        assert result is not None
        assert result.name == "Alice"
        assert result.seat == 0

    def test_get_player_at_seat_returns_none_for_unoccupied_seat(self, manager):
        """_get_player_at_seat returns None when no player is at the given seat."""
        game, _player, _conn = self._make_game_with_human(manager)

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

    def test_get_caller_seats_with_int_list(self, manager):
        """_get_caller_seats extracts seats from integer callers list."""
        assert manager._get_caller_seats([0, 1, 2]) == [0, 1, 2]

    def test_get_caller_seats_with_empty_list(self, manager):
        """_get_caller_seats returns empty list for empty callers."""
        assert manager._get_caller_seats([]) == []

    def test_get_caller_seats_deduplicates_meld_callers(self, manager):
        """_get_caller_seats returns unique seats when same player has multiple meld options."""
        callers = [
            MeldCaller(seat=0, call_type=MeldCallType.PON),
            MeldCaller(seat=0, call_type=MeldCallType.CHI, options=[(57, 63)]),
        ]
        assert manager._get_caller_seats(callers) == [0]

    def test_cleanup_timer_on_game_end_cancels_timer(self, manager):
        """_cleanup_timer_on_game_end cancels all player timers when GameEndedEvent is present."""
        game, _player, _conn = self._make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}

        game_end_event = ServiceEvent(
            event="game_end",
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
        game, _player, _conn = self._make_game_with_human(manager)

        generic_event = ServiceEvent(
            event="test",
            data=MockResultEvent(
                type="test",
                target="all",
                player="Alice",
                action="test",
                input={},
                success=True,
            ),
            target="all",
        )

        result = manager._cleanup_timer_on_game_end(game, [generic_event])
        assert result is False

    async def test_maybe_start_timer_with_turn_event(self, manager):
        """_maybe_start_timer starts a turn timer when TurnEvent targets the human player."""
        game, _player, _conn = self._make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        turn_event = ServiceEvent(
            event="turn",
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
        game, _player, _conn = self._make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        call_event = ServiceEvent(
            event="call_prompt",
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
        game, _player, _conn = self._make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}
        initial_bank = timer.remaining_bank

        round_event = ServiceEvent(
            event="round_started",
            data=RoundStartedEvent(
                type=EventType.ROUND_STARTED,
                target="seat_0",
                view=_make_dummy_game_view(),
            ),
            target="seat_0",
        )

        await manager._maybe_start_timer(game, [round_event])

        config = TimerConfig()
        assert timer.remaining_bank == initial_bank + config.round_bonus_seconds

    async def test_maybe_start_timer_with_round_end_event(self, manager):
        """_maybe_start_timer starts fixed round-advance timers when RoundEndEvent is present."""
        game, _player, _conn = self._make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        round_end_event = ServiceEvent(
            event="round_end",
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
        game, _player, _conn = self._make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = {0: timer}

        game_end_event = ServiceEvent(
            event="game_end",
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

    async def test_handle_timeout_executes_timeout_action(self, manager):
        """_handle_timeout invokes handle_timeout on the game service and broadcasts events."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)

        timeout_msgs = [m for m in conn.sent_messages if m.get("type") == "timeout_turn"]
        assert len(timeout_msgs) == 1

    async def test_maybe_start_timer_returns_when_timer_is_none(self, manager):
        """_maybe_start_timer returns early when no timer exists for the game."""
        game, _player, _conn = self._make_game_with_human(manager)
        # do not set up a timer for the game

        generic_event = ServiceEvent(
            event="test",
            data=MockResultEvent(
                type="test",
                target="all",
                player="Alice",
                action="test",
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
            event="turn",
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
        _game, _player, _conn = self._make_game_with_human(manager)
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


class TestSessionManagerGameEnd:
    """Tests for connection closing on game end."""

    @pytest.fixture
    def manager(self):
        game_service = MockGameService()
        return SessionManager(game_service)

    def _make_game_with_human(self, manager) -> tuple[Game, Player, MockConnection]:
        """Create a game with a human player who has an assigned seat."""
        conn = MockConnection()
        game = Game(game_id="game1")
        player = Player(connection=conn, name="Alice", game_id="game1", seat=0)
        game.players[conn.connection_id] = player
        manager._games["game1"] = game
        manager._players[conn.connection_id] = player
        manager._connections[conn.connection_id] = conn
        return game, player, conn

    def _make_game_end_event(self) -> ServiceEvent:
        return ServiceEvent(
            event="game_end",
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

    async def test_close_connections_on_game_end(self, manager):
        """All player connections are closed when game_end event is present."""
        game, _player, conn = self._make_game_with_human(manager)

        events = [self._make_game_end_event()]
        await manager._close_connections_on_game_end(game, events)

        assert conn.is_closed is True
        assert conn._close_code == 1000
        assert conn._close_reason == "game_ended"

    async def test_close_connections_skipped_without_game_end(self, manager):
        """Connections are not closed when no game_end event is present."""
        game, _player, conn = self._make_game_with_human(manager)

        generic_event = ServiceEvent(
            event="test",
            data=MockResultEvent(
                type="test",
                target="all",
                player="Alice",
                action="test",
                input={},
                success=True,
            ),
            target="all",
        )
        await manager._close_connections_on_game_end(game, [generic_event])

        assert conn.is_closed is False

    async def test_close_connections_on_game_end_multiple_players(self, manager):
        """All player connections are closed when game ends with multiple players."""
        game, _player, conn1 = self._make_game_with_human(manager)

        conn2 = MockConnection()
        player2 = Player(connection=conn2, name="Bob", game_id="game1", seat=1)
        game.players[conn2.connection_id] = player2

        events = [self._make_game_end_event()]
        await manager._close_connections_on_game_end(game, events)

        assert conn1.is_closed is True
        assert conn2.is_closed is True


class TestSessionManagerNumBots:
    """Tests for unified num_bots game creation in SessionManager."""

    @pytest.fixture
    def manager(self):
        game_service = MockGameService()
        return SessionManager(game_service)

    async def test_num_bots_0_does_not_start_on_first_join(self, manager):
        """Game with num_bots=0 does NOT auto-start when first player joins."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=0)

        await manager.join_game(conn, "game1", "Alice")

        game_started_events = [m for m in conn.sent_messages if m.get("type") == "game_started"]
        assert len(game_started_events) == 0

    async def test_num_bots_0_does_not_start_on_second_join(self, manager):
        """Game with num_bots=0 does NOT auto-start when 2nd player joins."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        for c in conns:
            game_started_events = [m for m in c.sent_messages if m.get("type") == "game_started"]
            assert len(game_started_events) == 0

    async def test_num_bots_0_does_not_start_on_third_join(self, manager):
        """Game with num_bots=0 does NOT auto-start when 3rd player joins."""
        conns = [MockConnection() for _ in range(3)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        for c in conns:
            game_started_events = [m for m in c.sent_messages if m.get("type") == "game_started"]
            assert len(game_started_events) == 0

    async def test_num_bots_0_starts_on_fourth_join(self, manager):
        """Game with num_bots=0 auto-starts when 4th player joins."""
        conns = [MockConnection() for _ in range(4)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        for c in conns:
            game_started_events = [m for m in c.sent_messages if m.get("type") == "game_started"]
            assert len(game_started_events) == 1

    async def test_num_bots_0_all_players_assigned_seats(self, manager):
        """All 4 human players are assigned seats after game starts."""
        conns = [MockConnection() for _ in range(4)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        game = manager.get_game("game1")
        for player in game.players.values():
            assert player.seat is not None

    async def test_num_bots_3_starts_on_first_join(self, manager):
        """Game with num_bots=3 (default) auto-starts on first join."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        game_started_events = [m for m in conn.sent_messages if m.get("type") == "game_started"]
        assert len(game_started_events) == 1

    async def test_num_bots_2_starts_on_second_join(self, manager):
        """Game with num_bots=2 auto-starts when 2nd human joins."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        game_started_events = [m for m in conns[0].sent_messages if m.get("type") == "game_started"]
        assert len(game_started_events) == 0

        await manager.join_game(conns[1], "game1", "Bob")
        for c in conns:
            game_started_events = [m for m in c.sent_messages if m.get("type") == "game_started"]
            assert len(game_started_events) == 1

    async def test_num_bots_1_starts_on_third_join(self, manager):
        """Game with num_bots=1 auto-starts when 3rd human joins."""
        conns = [MockConnection() for _ in range(3)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=1)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        for c in conns[:2]:
            game_started_events = [m for m in c.sent_messages if m.get("type") == "game_started"]
            assert len(game_started_events) == 0

        await manager.join_game(conns[2], "game1", "Charlie")
        for c in conns:
            game_started_events = [m for m in c.sent_messages if m.get("type") == "game_started"]
            assert len(game_started_events) == 1

    async def test_create_game_with_num_bots(self, manager):
        """create_game stores num_bots on the Game object."""
        manager.create_game("game1", num_bots=2)

        game = manager.get_game("game1")
        assert game.num_bots == 2

    async def test_create_game_default_num_bots(self, manager):
        """create_game without num_bots defaults to 3."""
        manager.create_game("game1")

        game = manager.get_game("game1")
        assert game.num_bots == 3

    async def test_create_game_invalid_num_bots(self):
        """Game rejects num_bots outside 0-3 range."""
        with pytest.raises(ValueError, match="num_bots must be 0-3"):
            Game(game_id="game1", num_bots=5)

        with pytest.raises(ValueError, match="num_bots must be 0-3"):
            Game(game_id="game1", num_bots=-1)

    async def test_get_games_info_includes_num_bots(self, manager):
        """get_games_info includes num_bots field for each game."""
        manager.create_game("game1", num_bots=3)
        manager.create_game("game2", num_bots=0)

        infos = manager.get_games_info()
        info_map = {info.game_id: info for info in infos}

        assert info_map["game1"].num_bots == 3
        assert info_map["game2"].num_bots == 0

    async def test_get_games_info_includes_started(self, manager):
        """get_games_info includes started field reflecting game state."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=3)
        manager.create_game("game2", num_bots=0)

        # game1 not started yet
        infos = manager.get_games_info()
        info_map = {info.game_id: info for info in infos}
        assert info_map["game1"].started is False
        assert info_map["game2"].started is False

        # start game1 by joining (num_bots=3, needs 1 human)
        await manager.join_game(conn, "game1", "Alice")

        infos = manager.get_games_info()
        info_map = {info.game_id: info for info in infos}
        assert info_map["game1"].started is True
        assert info_map["game2"].started is False


class TestPerPlayerTimers:
    """Tests for per-player timer independence."""

    @pytest.fixture
    def manager(self):
        game_service = MockGameService()
        return SessionManager(game_service)

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

    async def test_player_timers_are_independent_instances(self, manager):
        """Each player gets a separate TurnTimer instance."""
        conns = [MockConnection() for _ in range(4)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        timers = manager._timers["game1"]
        timer_ids = [id(t) for t in timers.values()]
        # all timers should be different objects
        assert len(set(timer_ids)) == 4

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
            event="round_started",
            data=RoundStartedEvent(
                type=EventType.ROUND_STARTED,
                target="seat_0",
                view=_make_dummy_game_view(),
            ),
            target="seat_0",
        )

        await manager._maybe_start_timer(game, [round_event])

        config = TimerConfig()
        assert timer0.remaining_bank == initial_bank_0 + config.round_bonus_seconds
        assert timer1.remaining_bank == initial_bank_1 + config.round_bonus_seconds

    async def test_game_end_cancels_all_player_timers(self, manager):
        """Game cleanup cancels all player timers."""
        game, _p1, _p2, _c1, _c2 = self._make_pvp_game_with_two_humans(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timers["game1"] = {0: timer0, 1: timer1}

        game_end_event = ServiceEvent(
            event="game_end",
            data=GameEndedEvent(
                type=EventType.GAME_END,
                target="all",
                result=GameEndResult(
                    winner_seat=0,
                    standings=[
                        PlayerStanding(seat=0, name="Alice", score=25000, final_score=0, is_bot=False),
                        PlayerStanding(seat=1, name="Bob", score=25000, final_score=0, is_bot=False),
                    ],
                ),
            ),
            target="all",
        )

        result = manager._cleanup_timer_on_game_end(game, [game_end_event])
        assert result is True

    async def test_multiple_meld_timers_for_multiple_callers(self, manager):
        """When 2+ humans can call the same discard, each gets their own meld timer."""
        game, _p1, _p2, _c1, _c2 = self._make_pvp_game_with_two_humans(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        # both seat 0 and seat 1 can call
        call_event = ServiceEvent(
            event="call_prompt",
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
            event="call_prompt",
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
        await manager.handle_game_action(conn1, "test_action", {})

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
            event="call_prompt",
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
        await manager.handle_game_action(conn1, "pass", {})

        # seat 0's timer should be stopped, seat 1's timer should still be running
        assert timer0._active_task is None
        assert timer1._active_task is not None
        timer1.cancel()

    async def test_partial_pass_does_not_cancel_other_timers(self, manager):
        """When a pass returns empty events, other callers' meld timers keep running."""
        game, _p1, _p2, conn1, _c2 = self._make_pvp_game_with_two_humans(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        # start meld timers for both callers
        call_event = ServiceEvent(
            event="call_prompt",
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

        # mock returns empty events (partial pass)
        manager._game_service.handle_action = AsyncMock(return_value=[])
        conn1._outbox.clear()
        await manager.handle_game_action(conn1, "pass", {})

        # seat 1's meld timer is still running (not cancelled)
        assert timer1._active_task is not None
        assert not timer1._active_task.done()
        timer1.cancel()

    async def test_turn_timer_starts_for_specific_player(self, manager):
        """Turn timer starts only for the player whose turn it is."""
        game, _p1, _p2, _c1, _c2 = self._make_pvp_game_with_two_humans(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        turn_event = ServiceEvent(
            event="turn",
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


class TestSessionManagerDisconnect:
    """Tests for disconnect handling."""

    @pytest.fixture
    def manager(self):
        game_service = MockGameService()
        return SessionManager(game_service)

    async def test_reject_join_after_game_started_num_bots_0(self, manager):
        """Joining a started game with num_bots=0 is rejected."""
        conns = [MockConnection() for _ in range(5)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i in range(4):
            await manager.join_game(conns[i], "game1", f"Player{i}")

        game = manager.get_game("game1")
        assert game.started is True

        await manager.join_game(conns[4], "game1", "Latecomer")

        error_msgs = [m for m in conns[4].sent_messages if m.get("type") == "session_error"]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == "game_started"

    async def test_reject_join_after_game_started_num_bots_3(self, manager):
        """Joining a started game with num_bots=3 is also rejected."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=3)

        await manager.join_game(conn1, "game1", "Alice")

        game = manager.get_game("game1")
        assert game.started is True

        await manager.join_game(conn2, "game1", "Bob")

        error_msgs = [m for m in conn2.sent_messages if m.get("type") == "session_error"]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == "game_started"

    async def test_disconnect_from_bot_game_cleans_up(self, manager):
        """Disconnecting from a num_bots=3 game cleans up when empty."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=3)
        await manager.join_game(conn, "game1", "Alice")

        game = manager.get_game("game1")
        assert game.started is True

        await manager.leave_game(conn)

        assert manager.get_game("game1") is None

    async def test_disconnect_replaces_human_with_bot(self, manager):
        """Disconnecting a human from a started multi-human game calls replace_player_with_bot."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        game = manager.get_game("game1")
        assert game.started is True

        # track replace_player_with_bot calls
        replace_calls = []
        original_replace = manager._game_service.replace_player_with_bot

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_player_with_bot = tracking_replace

        await manager.leave_game(conns[0])

        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", "Alice")
        # game should still exist (Bob is still in)
        assert manager.get_game("game1") is not None

    async def test_last_human_disconnect_does_not_replace_with_bot(self, manager):
        """When the last human leaves, bot replacement is skipped and the game is cleaned up."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        game = manager.get_game("game1")
        assert game.started is True

        replace_calls = []
        original_replace = manager._game_service.replace_player_with_bot

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_player_with_bot = tracking_replace

        # first player leaves (triggers bot replacement)
        await manager.leave_game(conns[0])
        assert len(replace_calls) == 1

        # second player leaves (last human -- no bot replacement, game cleaned up)
        await manager.leave_game(conns[1])
        assert len(replace_calls) == 1  # no additional call
        assert manager.get_game("game1") is None

    async def test_disconnect_cancels_player_timer(self, manager):
        """Disconnecting a human cancels their timer in the timers dict."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        # verify timers exist for both seats
        assert 0 in manager._timers["game1"]
        assert 1 in manager._timers["game1"]

        await manager.leave_game(conns[0])

        # seat 0's timer should be removed from the dict
        assert 0 not in manager._timers["game1"]
        # seat 1's timer should remain
        assert 1 in manager._timers["game1"]

    async def test_disconnect_from_non_started_game_does_not_replace(self, manager):
        """Disconnecting from a game that has not started does not trigger bot replacement."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=0)

        await manager.join_game(conn, "game1", "Alice")

        game = manager.get_game("game1")
        assert game.started is False

        replace_calls = []
        original_replace = manager._game_service.replace_player_with_bot

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_player_with_bot = tracking_replace

        await manager.leave_game(conn)

        assert len(replace_calls) == 0
        assert manager.get_game("game1") is None

    async def test_bot_replacement_broadcasts_events(self, manager):
        """When bot replacement produces events, they are broadcast to remaining players."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")
        conns[1]._outbox.clear()

        # make process_bot_actions_after_replacement return an event
        bot_event = ServiceEvent(
            event="test_bot_action",
            data=MockResultEvent(
                type="test_bot_action",
                target="all",
                player="Bot",
                action="discard",
                input={},
                success=True,
            ),
            target="all",
        )
        manager._game_service.process_bot_actions_after_replacement = AsyncMock(return_value=[bot_event])

        await manager.leave_game(conns[0])

        # Bob should receive the bot action event
        bot_msgs = [m for m in conns[1].sent_messages if m.get("type") == "test_bot_action"]
        assert len(bot_msgs) == 1

    async def test_stale_timeout_after_replacement_is_noop(self, manager):
        """A timeout callback for a replaced player's seat is safely ignored."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        # Alice disconnects
        await manager.leave_game(conns[0])
        conns[1]._outbox.clear()

        # stale timeout fires for Alice's old seat (seat 0)
        # should be a no-op because _get_player_at_seat returns None for seat 0
        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)

        assert len(conns[1].sent_messages) == 0

    async def test_disconnect_during_start_game_replaces_with_bot(self, manager):
        """Player disconnecting during start_game (before seat assignment) triggers bot replacement."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")

        # patch start_game to simulate a disconnect happening during the await.
        # remove Alice from game.players (as leave_game would) before
        # _start_mahjong_game can assign seats.
        original_start = manager._game_service.start_game
        game = manager.get_game("game1")

        async def disconnecting_start(game_id, player_names):
            result = await original_start(game_id, player_names)
            # simulate Alice disconnecting during start_game
            for conn_id, player in list(game.players.items()):
                if player.name == "Alice":
                    game.players.pop(conn_id)
                    player.game_id = None
                    break
            return result

        manager._game_service.start_game = disconnecting_start

        replace_calls = []
        original_replace = manager._game_service.replace_player_with_bot

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_player_with_bot = tracking_replace

        # join Bob -- triggers start; Alice is removed during start_game
        await manager.join_game(conns[1], "game1", "Bob")

        # post-start recovery should detect Alice disconnected and replace with bot
        assert ("game1", "Alice") in replace_calls

    async def test_disconnect_during_start_cancels_timer_and_broadcasts(self, manager):
        """Post-start recovery cancels the disconnected player's timer and broadcasts bot events."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")

        original_start = manager._game_service.start_game
        game = manager.get_game("game1")

        # remove Alice AFTER timer creation by injecting the removal
        # between timer setup and the lock acquisition in _start_mahjong_game.
        # we achieve this by removing her after start_game returns but ensuring
        # the timer loop still sees her (she's in game.players during that loop).
        alice_removed = False

        async def late_disconnecting_start(game_id, player_names):
            return await original_start(game_id, player_names)

        manager._game_service.start_game = late_disconnecting_start

        # patch _broadcast_events to remove Alice just before the recovery loop runs.
        # the first call to _broadcast_events is for start events, then the recovery loop
        # checks connected_names. we remove Alice after the seat/timer assignment but
        # before the lock block re-checks game.player_names.
        original_broadcast = manager._broadcast_events

        async def removing_broadcast(g, events):
            nonlocal alice_removed
            await original_broadcast(g, events)
            if not alice_removed:
                alice_removed = True
                for conn_id, player in list(game.players.items()):
                    if player.name == "Alice":
                        game.players.pop(conn_id)
                        player.game_id = None
                        break

        manager._broadcast_events = removing_broadcast

        # mock process_bot_actions_after_replacement to return an event
        bot_event = ServiceEvent(
            event="test_bot_action",
            data=MockResultEvent(
                type="test_bot_action",
                target="all",
                player="Bot",
                action="discard",
                input={},
                success=True,
            ),
            target="all",
        )
        manager._game_service.process_bot_actions_after_replacement = AsyncMock(return_value=[bot_event])

        # join Bob -- triggers start; Alice is removed during first broadcast
        await manager.join_game(conns[1], "game1", "Bob")

        # Bob should receive the bot action event
        bot_msgs = [m for m in conns[1].sent_messages if m.get("type") == "test_bot_action"]
        assert len(bot_msgs) == 1

    async def test_replace_with_bot_returns_when_lock_missing(self, manager):
        """_replace_with_bot returns early when game lock has been cleaned up."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        game = manager.get_game("game1")

        # remove the game lock to simulate cleanup race
        manager._game_locks.pop("game1", None)

        process_calls = []
        original_process = manager._game_service.process_bot_actions_after_replacement

        async def tracking_process(game_id, seat):
            process_calls.append((game_id, seat))
            return await original_process(game_id, seat)

        manager._game_service.process_bot_actions_after_replacement = tracking_process

        # directly call _replace_with_bot (lock is missing)
        await manager._replace_with_bot(game, "Alice", 0)

        # replace_player_with_bot was called but process_bot_actions was NOT
        # (early return due to missing lock)
        assert len(process_calls) == 0


class TestHeartbeat:
    """Tests for heartbeat (ping/pong) and per-game heartbeat monitor."""

    @pytest.fixture
    def manager(self):
        game_service = MockGameService()
        return SessionManager(game_service)

    async def test_ping_responds_with_pong(self, manager):
        """handle_ping sends a pong message and updates last activity timestamp."""
        conn = MockConnection()
        manager.register_connection(conn)
        initial_time = manager._last_ping[conn.connection_id]

        # small delay so monotonic time advances
        await asyncio.sleep(0.01)
        await manager.handle_ping(conn)

        assert len(conn.sent_messages) == 1
        assert conn.sent_messages[0]["type"] == SessionMessageType.PONG
        assert manager._last_ping[conn.connection_id] > initial_time

    async def test_register_connection_initializes_ping_timestamp(self, manager):
        """register_connection sets initial ping timestamp."""
        conn = MockConnection()
        manager.register_connection(conn)

        assert conn.connection_id in manager._last_ping
        assert isinstance(manager._last_ping[conn.connection_id], float)

    async def test_unregister_connection_cleans_up_ping_tracking(self, manager):
        """unregister_connection removes ping tracking."""
        conn = MockConnection()
        manager.register_connection(conn)
        assert conn.connection_id in manager._last_ping

        manager.unregister_connection(conn)
        assert conn.connection_id not in manager._last_ping

    async def test_heartbeat_monitor_disconnects_stale_connection(self, manager):
        """Heartbeat monitor disconnects connections that haven't pinged within timeout."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")

        game = manager.get_game("game1")
        assert game is not None

        # set the last ping to well past the timeout
        manager._last_ping[conn.connection_id] = time.monotonic() - HEARTBEAT_TIMEOUT - 10

        # manually add the game to internal state (bypass start for this test)
        # and run one iteration of the heartbeat check
        with patch("game.session.manager.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await manager._heartbeat_loop("game1")

        assert conn.is_closed

    async def test_heartbeat_monitor_keeps_active_connections(self, manager):
        """Heartbeat monitor does not disconnect connections with recent pings."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")

        # last ping is fresh (just registered)
        with patch("game.session.manager.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await manager._heartbeat_loop("game1")

        assert not conn.is_closed

    async def test_heartbeat_starts_with_game(self, manager):
        """Heartbeat task is created when the game starts."""
        conns = [MockConnection() for _ in range(4)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        assert "game1" in manager._heartbeat_tasks
        task = manager._heartbeat_tasks["game1"]
        assert not task.done()

        # clean up: cancel the heartbeat task
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def test_heartbeat_stops_on_game_cleanup(self, manager):
        """Heartbeat task is cancelled when game becomes empty."""
        conns = [MockConnection() for _ in range(4)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        assert "game1" in manager._heartbeat_tasks
        heartbeat_task = manager._heartbeat_tasks["game1"]

        # leave all players -- game becomes empty, cleanup runs
        for c in conns:
            await manager.leave_game(c)

        assert "game1" not in manager._heartbeat_tasks
        assert heartbeat_task.done()

    async def test_heartbeat_loop_stops_when_game_removed(self, manager):
        """Heartbeat loop returns when the game is no longer in the games dict."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")

        # remove the game from the dict
        manager._games.pop("game1", None)

        with patch("game.session.manager.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.return_value = None
            # should return without error when game is missing
            await manager._heartbeat_loop("game1")

        assert not conn.is_closed
