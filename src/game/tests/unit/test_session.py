import asyncio

import pytest

from game.logic.enums import CallType, TimeoutType
from game.logic.mock import MockGameService, MockResultEvent
from game.logic.timer import TimerConfig, TurnTimer
from game.logic.types import GameEndResult, GameView, PlayerStanding, PlayerView
from game.messaging.events import (
    CallPromptEvent,
    GameEndedEvent,
    RoundStartedEvent,
    ServiceEvent,
    TurnEvent,
)
from game.messaging.mock import MockConnection
from game.messaging.types import ServerMessageType
from game.session.manager import SessionManager
from game.session.models import Game, Player


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
        assert msg["type"] == ServerMessageType.GAME_JOINED

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
        manager.create_game("game1")

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        # conn1 should have received: game_joined + game_started + player_joined
        player_joined_msgs = [
            m for m in conn1.sent_messages if m.get("type") == ServerMessageType.PLAYER_JOINED
        ]
        assert len(player_joined_msgs) == 1
        assert player_joined_msgs[0]["player_name"] == "Bob"

    async def test_leave_game_notifies_others(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1")

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        # clear previous messages
        conn1._outbox.clear()

        await manager.leave_game(conn2)

        assert len(conn1.sent_messages) == 1
        assert conn1.sent_messages[0]["type"] == ServerMessageType.PLAYER_LEFT
        assert conn1.sent_messages[0]["player_name"] == "Bob"

    async def test_game_full_error(self, manager):
        connections = [MockConnection() for _ in range(5)]
        for conn in connections:
            manager.register_connection(conn)
        manager.create_game("game1")

        # join 4 players (max)
        for i, conn in enumerate(connections[:4]):
            await manager.join_game(conn, "game1", f"Player{i}")

        # 5th player should get error
        await manager.join_game(connections[4], "game1", "Player4")

        msg = connections[4].sent_messages[0]
        assert msg["type"] == ServerMessageType.ERROR
        assert msg["code"] == "game_full"

    async def test_duplicate_name_error(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1")

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Alice")

        msg = conn2.sent_messages[0]
        assert msg["type"] == ServerMessageType.ERROR
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
        assert msg["type"] == ServerMessageType.ERROR
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
        manager.create_game("game1")

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
        manager.create_game("game1")

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

    async def test_start_game_not_called_on_second_player(self, manager):
        """start_game is called once when first player joins, not on subsequent joins."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1")

        await manager.join_game(conn1, "game1", "Alice")

        conn1._outbox.clear()
        await manager.join_game(conn2, "game1", "Bob")

        # conn1 should not receive any new game_started events
        new_game_started = [m for m in conn1.sent_messages if m.get("type") == "game_started"]
        assert len(new_game_started) == 0


class TestSessionManagerTimers:
    @pytest.fixture
    def manager(self):
        game_service = MockGameService()
        return SessionManager(game_service)

    async def test_timer_created_on_game_start(self, manager):
        """Timer is created when a game starts."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        assert "game1" in manager._timers
        assert isinstance(manager._timers["game1"], TurnTimer)

    async def test_lock_created_on_game_start(self, manager):
        """Asyncio lock is created when a game starts."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        assert "game1" in manager._game_locks

    async def test_timer_gets_initial_round_bonus(self, manager):
        """Timer receives the first round bonus on game start."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        timer = manager._timers["game1"]
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
        assert msg["type"] == ServerMessageType.ERROR
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
        assert msg["type"] == ServerMessageType.ERROR
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

    def test_cleanup_timer_on_game_end_cancels_timer(self, manager):
        """_cleanup_timer_on_game_end cancels active timer when GameEndedEvent is present."""
        game, _player, _conn = self._make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = timer

        game_end_event = ServiceEvent(
            event="game_end",
            data=GameEndedEvent(
                type="game_end",
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
        manager._timers["game1"] = timer
        manager._game_locks["game1"] = asyncio.Lock()

        turn_event = ServiceEvent(
            event="turn",
            data=TurnEvent(
                type="turn",
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
        manager._timers["game1"] = timer
        manager._game_locks["game1"] = asyncio.Lock()

        call_event = ServiceEvent(
            event="call_prompt",
            data=CallPromptEvent(
                type="call_prompt",
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
        """_maybe_start_timer adds round bonus when RoundStartedEvent is present."""
        game, _player, _conn = self._make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = timer
        initial_bank = timer.remaining_bank

        round_event = ServiceEvent(
            event="round_started",
            data=RoundStartedEvent(
                type="round_started",
                target="seat_0",
                view=_make_dummy_game_view(),
            ),
            target="seat_0",
        )

        await manager._maybe_start_timer(game, [round_event])

        config = TimerConfig()
        assert timer.remaining_bank == initial_bank + config.round_bonus_seconds

    async def test_maybe_start_timer_with_game_ended_event(self, manager):
        """_maybe_start_timer returns early and cleans up timer when GameEndedEvent is present."""
        game, _player, _conn = self._make_game_with_human(manager)
        timer = TurnTimer()
        manager._timers["game1"] = timer

        game_end_event = ServiceEvent(
            event="game_end",
            data=GameEndedEvent(
                type="game_end",
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
        manager._timers["game1"] = timer

        turn_event = ServiceEvent(
            event="turn",
            data=TurnEvent(
                type="turn",
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
                type="game_end",
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
