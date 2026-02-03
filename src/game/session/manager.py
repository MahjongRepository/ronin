import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

from game.logic.enums import TimeoutType
from game.logic.timer import TurnTimer
from game.messaging.events import (
    CallPromptEvent,
    ErrorEvent,
    FuritenEvent,
    GameEndedEvent,
    RoundEndEvent,
    RoundStartedEvent,
    TurnEvent,
)
from game.messaging.types import (
    ErrorMessage,
    GameJoinedMessage,
    GameLeftMessage,
    PlayerJoinedMessage,
    PlayerLeftMessage,
    PongMessage,
    SessionChatMessage,
)
from game.session.models import Game, Player
from game.session.types import GameInfo
from shared.logging import rotate_log_file

HEARTBEAT_CHECK_INTERVAL = 5  # seconds between heartbeat checks
HEARTBEAT_TIMEOUT = 30  # seconds before disconnecting an idle client
ROUND_ADVANCE_TIMEOUT = 15  # seconds to confirm round advancement

if TYPE_CHECKING:
    from game.logic.service import GameService
    from game.logic.types import MeldCaller
    from game.messaging.events import ServiceEvent
    from game.messaging.protocol import ConnectionProtocol

logger = logging.getLogger(__name__)


class SessionManager:
    MAX_PLAYERS_PER_GAME = 4  # Mahjong requires exactly 4 players

    def __init__(self, game_service: GameService, log_dir: str | None = None) -> None:
        self._game_service = game_service
        self._log_dir = log_dir
        self._connections: dict[str, ConnectionProtocol] = {}
        self._players: dict[str, Player] = {}  # connection_id -> Player
        self._games: dict[str, Game] = {}  # game_id -> Game
        self._timers: dict[str, dict[int, TurnTimer]] = {}  # game_id -> {seat -> TurnTimer}
        self._game_locks: dict[str, asyncio.Lock] = {}  # game_id -> Lock
        self._last_ping: dict[str, float] = {}  # connection_id -> monotonic timestamp
        self._heartbeat_tasks: dict[str, asyncio.Task[None]] = {}  # game_id -> heartbeat task

    def register_connection(self, connection: ConnectionProtocol) -> None:
        self._connections[connection.connection_id] = connection
        self._last_ping[connection.connection_id] = time.monotonic()

    def unregister_connection(self, connection: ConnectionProtocol) -> None:
        self._connections.pop(connection.connection_id, None)
        self._players.pop(connection.connection_id, None)
        self._last_ping.pop(connection.connection_id, None)

    def get_player(self, connection: ConnectionProtocol) -> Player | None:
        return self._players.get(connection.connection_id)

    def get_game(self, game_id: str) -> Game | None:
        return self._games.get(game_id)

    @property
    def game_count(self) -> int:
        return len(self._games)

    def get_games_info(self) -> list[GameInfo]:
        """
        Return info about all active games for the lobby list.
        """
        return [
            GameInfo(
                game_id=game.game_id,
                player_count=game.player_count,
                max_players=self.MAX_PLAYERS_PER_GAME,
                num_bots=game.num_bots,
                started=game.started,
            )
            for game in self._games.values()
        ]

    def create_game(self, game_id: str, num_bots: int = 3) -> Game:
        if self._log_dir:
            rotate_log_file(self._log_dir)
        game = Game(game_id=game_id, num_bots=num_bots)
        self._games[game_id] = game
        logger.info(f"game created: {game_id} num_bots={num_bots}")
        return game

    async def _send_error(self, connection: ConnectionProtocol, code: str, message: str) -> None:
        await connection.send_message(ErrorMessage(code=code, message=message).model_dump())

    async def join_game(
        self,
        connection: ConnectionProtocol,
        game_id: str,
        player_name: str,
    ) -> None:
        # check if already in a game
        existing_player = self._players.get(connection.connection_id)
        if existing_player and existing_player.game_id:
            await self._send_error(connection, "already_in_game", "You must leave your current game first")
            return

        game = self._games.get(game_id)
        if game is None:
            await self._send_error(connection, "game_not_found", "Game does not exist")
            return

        # block all joins to started or full games
        if game.started:
            await self._send_error(connection, "game_started", "Game has already started")
            return

        if game.player_count >= game.num_humans_needed:
            await self._send_error(connection, "game_full", "Game is full")
            return

        # check for duplicate name in game
        if player_name in [p.name for p in game.players.values()]:
            await self._send_error(connection, "name_taken", "That name is already taken in this game")
            return

        # create player and add to game
        player = Player(connection=connection, name=player_name, game_id=game_id)
        self._players[connection.connection_id] = player
        game.players[connection.connection_id] = player
        logger.info(f"player '{player_name}' joined game {game_id}")

        # notify the joining player
        await connection.send_message(
            GameJoinedMessage(
                game_id=game_id,
                players=game.player_names,
            ).model_dump()
        )

        # notify other players in the game
        await self._broadcast_to_game(
            game=game,
            message=PlayerJoinedMessage(player_name=player_name).model_dump(),
            exclude_connection_id=connection.connection_id,
        )

        # start when enough humans have joined.
        # game.started is set synchronously in _start_mahjong_game()
        # before any await, preventing double-start from concurrent joins.
        if not game.started and game.player_count == game.num_humans_needed:
            await self._start_mahjong_game(game)

    async def leave_game(
        self,
        connection: ConnectionProtocol,
        *,
        notify_player: bool = True,
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            return

        game = self._games.get(player.game_id)
        if game is None:
            return

        player_name = player.name
        player_seat = player.seat
        logger.info(f"player '{player_name}' left game {player.game_id}")

        # remove player from game
        game.players.pop(connection.connection_id, None)
        player.game_id = None

        # notify the leaving player (ignore errors if connection is already closed)
        if notify_player:
            with contextlib.suppress(RuntimeError, OSError):
                await connection.send_message(GameLeftMessage().model_dump())

        # notify remaining players
        await self._broadcast_to_game(
            game=game,
            message=PlayerLeftMessage(player_name=player_name).model_dump(),
        )

        # replace disconnected human with bot in a started game
        # (only if other humans remain -- no point running all-bot games)
        if game.started and not game.is_empty and player_seat is not None:
            await self._replace_with_bot(game, player_name, player_seat)

        # clean up empty games (use pop to ensure only one task performs cleanup)
        if game.is_empty and self._games.pop(game.game_id, None) is not None:
            logger.info(f"game {game.game_id} is empty, cleaning up")
            timers = self._timers.pop(game.game_id, None)
            if timers:
                for timer in timers.values():
                    timer.cancel()
            self._game_locks.pop(game.game_id, None)
            await self._stop_heartbeat_for_game(game.game_id)
            self._game_service.cleanup_game(game.game_id)

    async def _replace_with_bot(self, game: Game, player_name: str, seat: int) -> None:
        """
        Replace a disconnected human with a bot and process any pending bot actions.

        Must be called BEFORE the is_empty cleanup check, and only when other
        humans remain in the game.
        """
        self._game_service.replace_player_with_bot(game.game_id, player_name)

        # cancel the disconnected player's timer to prevent stale callbacks
        timers = self._timers.get(game.game_id)
        if timers:
            player_timer = timers.pop(seat, None)
            if player_timer:
                player_timer.cancel()

        # process bot actions if the replaced player had a pending turn or call.
        # if _handle_timeout already processed this seat's action before we acquired
        # the lock, process_bot_actions_after_replacement safely returns empty events
        # (the game state has already advanced past this seat's turn/call).
        lock = self._game_locks.get(game.game_id)
        if lock is None:
            return

        async with lock:
            events = await self._game_service.process_bot_actions_after_replacement(game.game_id, seat)
            if events:
                await self._broadcast_events(game, events)
                await self._maybe_start_timer(game, events)
                await self._close_connections_on_game_end(game, events)

    async def handle_game_action(
        self,
        connection: ConnectionProtocol,
        action: str,
        data: dict[str, Any],
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            await self._send_error(connection, "not_in_game", "You must join a game first")
            return

        game = self._games.get(player.game_id)
        if game is None:
            return

        game_id = player.game_id
        lock = self._game_locks.setdefault(game_id, asyncio.Lock())

        async with lock:
            events = await self._game_service.handle_action(
                game_id=game_id,
                player_name=player.name,
                action=action,
                data=data,
            )

            # failed actions (errors) should not consume bank time or cancel timers.
            # successful actions that produce no events (e.g. partial pass while
            # other callers are still pending) still stop the acting player's timer
            # but don't cancel other players' meld timers.
            timers = self._timers.get(game_id)
            if timers and player.seat is not None and not self._has_error_events(events):
                player_timer = timers.get(player.seat)
                if player_timer:
                    player_timer.stop()
                # cancel meld timers for other players only when the prompt resolved
                if self._has_game_events(events):
                    for seat, timer in timers.items():
                        if seat != player.seat:
                            timer.cancel()

            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)
            await self._close_connections_on_game_end(game, events)

    async def broadcast_chat(
        self,
        connection: ConnectionProtocol,
        text: str,
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            await self._send_error(connection, "not_in_game", "You must join a game first")
            return

        game = self._games.get(player.game_id)
        if game is None:
            return

        await self._broadcast_to_game(
            game=game,
            message=SessionChatMessage(
                player_name=player.name,
                text=text,
            ).model_dump(),
        )

    async def handle_ping(self, connection: ConnectionProtocol) -> None:
        """Respond to client ping with pong and update activity timestamp."""
        self._last_ping[connection.connection_id] = time.monotonic()
        await connection.send_message(PongMessage().model_dump())

    def _start_heartbeat_for_game(self, game_id: str) -> None:
        """Start the heartbeat monitor for a specific game."""
        self._heartbeat_tasks[game_id] = asyncio.create_task(self._heartbeat_loop(game_id))

    async def _stop_heartbeat_for_game(self, game_id: str) -> None:
        """Stop the heartbeat monitor for a specific game."""
        task = self._heartbeat_tasks.pop(game_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _heartbeat_loop(self, game_id: str) -> None:
        """Periodically check for stale connections in a specific game."""
        while True:
            await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL)
            game = self._games.get(game_id)
            if game is None:
                return

            now = time.monotonic()
            for player in list(game.players.values()):
                conn_id = player.connection_id
                last_ping = self._last_ping.get(conn_id)
                if last_ping is not None and now - last_ping > HEARTBEAT_TIMEOUT:
                    connection = self._connections.get(conn_id)
                    if connection:
                        logger.info(f"heartbeat timeout for {conn_id} in game {game_id}, disconnecting")
                        with contextlib.suppress(RuntimeError, OSError, ConnectionError):
                            await connection.close(code=1000, reason="heartbeat_timeout")

    async def _start_mahjong_game(self, game: Game) -> None:
        """
        Start the mahjong game when num_humans_needed players have joined.
        """
        game.started = True
        player_names = game.player_names
        events = await self._game_service.start_game(game.game_id, player_names)

        # assign seats to session players still connected after the await
        for player in game.players.values():
            seat = self._game_service.get_player_seat(game.game_id, player.name)
            if seat is not None:
                player.seat = seat

        # create per-player timers and lock for this game
        timers: dict[int, TurnTimer] = {}
        for player in game.players.values():
            if player.seat is not None:
                timers[player.seat] = TurnTimer()
        self._timers[game.game_id] = timers
        self._game_locks[game.game_id] = asyncio.Lock()
        self._start_heartbeat_for_game(game.game_id)

        async with self._game_locks[game.game_id]:
            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)

            # replace players who disconnected during start_game or the
            # subsequent broadcasts (before leave_game could do bot replacement
            # because seats/locks were not yet set up).
            connected_names = set(game.player_names)
            for name in player_names:
                if name not in connected_names and not game.is_empty:
                    seat = self._game_service.get_player_seat(game.game_id, name)
                    if seat is not None:
                        self._game_service.replace_player_with_bot(game.game_id, name)
                        # remove stale timer for the disconnected player's seat
                        player_timer = timers.pop(seat, None)
                        if player_timer:
                            player_timer.cancel()
                        bot_events = await self._game_service.process_bot_actions_after_replacement(
                            game.game_id, seat
                        )
                        if bot_events:
                            await self._broadcast_events(game, bot_events)
                            await self._maybe_start_timer(game, bot_events)
                            await self._close_connections_on_game_end(game, bot_events)

    async def _broadcast_events(
        self,
        game: Game,
        events: list[ServiceEvent],
    ) -> None:
        """
        Broadcast events with target-based filtering.

        Events with target "all" go to everyone, except CallPromptEvent
        which is only sent to the players listed in its callers field.
        Events with target "seat_N" go only to the player at that seat.
        """
        # build seat -> player mapping using assigned seats
        seat_to_player = {p.seat: p for p in game.players.values() if p.seat is not None}

        for event in events:
            message = {"type": event.event, **event.data.model_dump(exclude={"type", "target"})}

            if isinstance(event.data, CallPromptEvent):
                # only send call prompts to seats listed in callers
                for seat in self._get_caller_seats(event.data.callers):
                    player = seat_to_player.get(seat)
                    if player:
                        with contextlib.suppress(RuntimeError, OSError):
                            await player.connection.send_message(message)
            elif event.target == "all":
                await self._broadcast_to_game(game, message)
            elif event.target.startswith("seat_"):
                seat = int(event.target.split("_")[1])
                player = seat_to_player.get(seat)
                if player:
                    # ignore connection errors, will be cleaned up on disconnect
                    with contextlib.suppress(RuntimeError, OSError):
                        await player.connection.send_message(message)

    async def _broadcast_to_game(
        self,
        game: Game,
        message: dict[str, Any],
        exclude_connection_id: str | None = None,
    ) -> None:
        for player in game.players.values():
            if player.connection_id != exclude_connection_id:
                # ignore connection errors, will be cleaned up on disconnect
                with contextlib.suppress(RuntimeError, OSError):
                    await player.connection.send_message(message)

    async def _maybe_start_timer(self, game: Game, events: list[ServiceEvent]) -> None:
        """
        Inspect events and start appropriate timer if a connected player needs to act.
        """
        if self._cleanup_timer_on_game_end(game, events):
            return

        timers = self._timers.get(game.game_id)
        if timers is None:
            return

        # add round bonus to all player timers when a new round starts
        if any(isinstance(event.data, RoundStartedEvent) for event in events):
            for timer in timers.values():
                timer.add_round_bonus()

        # check for round end events -- start round advance timers for human players
        if any(isinstance(event.data, RoundEndEvent) for event in events):
            self._start_round_advance_timers(game, timers)
            return

        if self._start_turn_timer_from_events(game, timers, events):
            return

        # start meld timers for all connected callers (PvP can have multiple human callers)
        game_id = game.game_id
        caller_seats = self._find_connected_caller_seats(game, events)
        for seat in caller_seats:
            timer = timers.get(seat)
            if timer is not None:
                timer.start_meld_timer(
                    lambda gid=game_id, s=seat: self._handle_timeout(gid, TimeoutType.MELD, s)
                )

    def _start_turn_timer_from_events(
        self, game: Game, timers: dict[int, TurnTimer], events: list[ServiceEvent]
    ) -> bool:
        """Start a turn timer if events contain a TurnEvent for a connected player."""
        game_id = game.game_id
        for event in events:
            if isinstance(event.data, TurnEvent):
                seat = event.data.current_seat
                timer = timers.get(seat)
                if timer is not None and self._get_player_at_seat(game, seat) is not None:
                    timer.start_turn_timer(
                        lambda gid=game_id, s=seat: self._handle_timeout(gid, TimeoutType.TURN, s)
                    )
                    return True
        return False

    def _start_round_advance_timers(self, game: Game, timers: dict[int, TurnTimer]) -> None:
        """Start fixed-duration timers for human players to confirm round advancement."""
        game_id = game.game_id
        for player in game.players.values():
            if player.seat is not None:
                timer = timers.get(player.seat)
                if timer is not None:
                    timer.start_fixed_timer(
                        ROUND_ADVANCE_TIMEOUT,
                        lambda gid=game_id, s=player.seat: self._handle_timeout(
                            gid, TimeoutType.ROUND_ADVANCE, s
                        ),
                    )

    def _cleanup_timer_on_game_end(self, game: Game, events: list[ServiceEvent]) -> bool:
        """
        Clean up timers when the game ends. Returns True if game ended.

        Only cancels the timers here. Lock and timer dict cleanup happens in leave_game
        when the game becomes empty, to avoid removing the lock while it is still held.
        """
        if not any(isinstance(event.data, GameEndedEvent) for event in events):
            return False
        timers = self._timers.get(game.game_id)
        if timers:
            for timer in timers.values():
                timer.cancel()
        return True

    async def close_game_on_error(self, connection: ConnectionProtocol) -> None:  # pragma: no cover
        """
        Close all player connections after an unrecoverable error.

        The WebSocket disconnect handlers will clean up session state
        (remove players, clean up empty game) when connections close.
        """
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            return

        game = self._games.get(player.game_id)
        if game is None:
            return

        for p in list(game.players.values()):
            with contextlib.suppress(RuntimeError, OSError):
                await p.connection.close(code=1011, reason="internal_error")

    async def _close_connections_on_game_end(self, game: Game, events: list[ServiceEvent]) -> None:
        """
        Close all player connections after the game ends.

        The WebSocket disconnect handlers will clean up session state
        (remove players, clean up empty game) when connections close.
        """
        if not any(isinstance(event.data, GameEndedEvent) for event in events):
            return
        for player in list(game.players.values()):
            with contextlib.suppress(RuntimeError, OSError):
                await player.connection.close(code=1000, reason="game_ended")

    def _get_player_at_seat(self, game: Game, seat: int) -> Player | None:
        for player in game.players.values():
            if player.seat == seat:
                return player
        return None

    def _has_game_events(self, events: list[ServiceEvent]) -> bool:
        return any(not isinstance(event.data, (ErrorEvent, FuritenEvent)) for event in events)

    def _has_error_events(self, events: list[ServiceEvent]) -> bool:
        return any(isinstance(event.data, ErrorEvent) for event in events)

    def _get_caller_seats(self, callers: list[int] | list[MeldCaller]) -> list[int]:
        # deduplicate: a player with both pon and chi options appears as multiple callers
        seen: set[int] = set()
        seats: list[int] = []
        for caller in callers:
            seat = caller if isinstance(caller, int) else caller.seat
            if seat not in seen:
                seen.add(seat)
                seats.append(seat)
        return seats

    def _find_connected_caller_seats(self, game: Game, events: list[ServiceEvent]) -> list[int]:
        """Return all connected human seats that have a pending meld decision."""
        seats: list[int] = []
        for event in events:
            if isinstance(event.data, CallPromptEvent):
                seats.extend(
                    seat
                    for seat in self._get_caller_seats(event.data.callers)
                    if self._get_player_at_seat(game, seat) is not None
                )
        return seats

    async def _handle_timeout(self, game_id: str, timeout_type: TimeoutType, seat: int) -> None:
        lock = self._game_locks.get(game_id)
        if lock is None:
            return

        async with lock:
            game = self._games.get(game_id)
            if game is None:
                return

            player = self._get_player_at_seat(game, seat)
            if player is None:
                return

            # only consume bank for TURN timeouts.
            # ROUND_ADVANCE and MELD timers use fixed durations (_turn_start_time is None),
            # so consume_bank() would be a no-op anyway, but being explicit is cleaner.
            if timeout_type == TimeoutType.TURN:
                timers = self._timers.get(game_id)
                if timers:
                    player_timer = timers.get(seat)
                    if player_timer:
                        player_timer.consume_bank()

            events = await self._game_service.handle_timeout(game_id, player.name, timeout_type)
            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)
            await self._close_connections_on_game_end(game, events)
