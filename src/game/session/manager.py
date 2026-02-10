import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    DrawEvent,
    ErrorEvent,
    FuritenEvent,
    GameEndedEvent,
    RoundEndEvent,
    RoundStartedEvent,
    SeatTarget,
)
from game.logic.timer import TimerConfig
from game.messaging.event_payload import service_event_payload, shape_call_prompt_payload
from game.messaging.types import (
    ErrorMessage,
    GameJoinedMessage,
    GameLeftMessage,
    PlayerJoinedMessage,
    PlayerLeftMessage,
    PongMessage,
    SessionChatMessage,
    SessionErrorCode,
)
from game.session.heartbeat import HeartbeatMonitor
from game.session.models import Game, Player
from game.session.timer_manager import TimerManager
from game.session.types import GameInfo
from shared.logging import rotate_log_file

if TYPE_CHECKING:
    from game.logic.events import ServiceEvent
    from game.logic.service import GameService
    from game.messaging.protocol import ConnectionProtocol
    from game.session.replay_collector import ReplayCollector

logger = logging.getLogger(__name__)


class SessionManager:
    MAX_PLAYERS_PER_GAME = 4  # Mahjong requires exactly 4 players

    def __init__(
        self,
        game_service: GameService,
        log_dir: str | None = None,
        replay_collector: ReplayCollector | None = None,
    ) -> None:
        self._game_service = game_service
        self._log_dir = log_dir
        self._replay_collector = replay_collector
        self._connections: dict[str, ConnectionProtocol] = {}
        self._players: dict[str, Player] = {}  # connection_id -> Player
        self._games: dict[str, Game] = {}  # game_id -> Game
        self._timer_manager = TimerManager(on_timeout=self._handle_timeout)
        self._game_locks: dict[str, asyncio.Lock] = {}  # game_id -> Lock
        self._heartbeat = HeartbeatMonitor()

    def _get_game_lock(self, game_id: str) -> asyncio.Lock | None:
        """Get the per-game lock, or None if the game has no lock (not yet started or already cleaned up)."""
        return self._game_locks.get(game_id)

    def register_connection(self, connection: ConnectionProtocol) -> None:
        self._connections[connection.connection_id] = connection
        self._heartbeat.record_connect(connection.connection_id)

    def unregister_connection(self, connection: ConnectionProtocol) -> None:
        self._connections.pop(connection.connection_id, None)
        self._players.pop(connection.connection_id, None)
        self._heartbeat.record_disconnect(connection.connection_id)

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

    def _start_replay_collection(self, game_id: str) -> None:
        """Start replay collection with the game seed (known after game_service.start_game)."""
        if self._replay_collector:
            seed = self._game_service.get_game_seed(game_id)
            if seed is not None:
                self._replay_collector.start_game(game_id, seed)

    async def _send_error(self, connection: ConnectionProtocol, code: SessionErrorCode, message: str) -> None:
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
            await self._send_error(
                connection,
                SessionErrorCode.ALREADY_IN_GAME,
                "You must leave your current game first",
            )
            return

        game = self._games.get(game_id)
        if game is None:
            await self._send_error(connection, SessionErrorCode.GAME_NOT_FOUND, "Game does not exist")
            return

        # block all joins to started or full games
        if game.started:
            await self._send_error(connection, SessionErrorCode.GAME_STARTED, "Game has already started")
            return

        if game.player_count >= game.num_humans_needed:
            await self._send_error(connection, SessionErrorCode.GAME_FULL, "Game is full")
            return

        # check for duplicate name in game
        if player_name in [p.name for p in game.players.values()]:
            await self._send_error(
                connection,
                SessionErrorCode.NAME_TAKEN,
                "That name is already taken in this game",
            )
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

        game_id = game.game_id
        player_name = player.name
        player_seat = player.seat
        logger.info(f"player '{player_name}' left game {game_id}")

        lock = self._get_game_lock(game_id) if game.started else None

        if lock is not None:
            # started game: guard all state mutation under the per-game lock
            # to prevent races with handle_game_action and timeout callbacks
            async with lock:
                self._remove_player_from_game(game, connection.connection_id, player)
                if notify_player:
                    with contextlib.suppress(RuntimeError, OSError):
                        await connection.send_message(GameLeftMessage().model_dump())
                await self._broadcast_to_game(
                    game=game,
                    message=PlayerLeftMessage(player_name=player_name).model_dump(),
                )
                # replace disconnected human with bot (only if other humans remain)
                if not game.is_empty and player_seat is not None:
                    await self._replace_with_bot(game, player_name, player_seat)
        else:
            # pre-start game: no lock needed (no concurrent action/timeout paths)
            self._remove_player_from_game(game, connection.connection_id, player)
            if notify_player:
                with contextlib.suppress(RuntimeError, OSError):
                    await connection.send_message(GameLeftMessage().model_dump())
            await self._broadcast_to_game(
                game=game,
                message=PlayerLeftMessage(player_name=player_name).model_dump(),
            )

        # clean up empty games (use pop to ensure only one task performs cleanup)
        if game.is_empty and self._games.pop(game_id, None) is not None:
            logger.info(f"game {game_id} is empty, cleaning up")
            self._timer_manager.cleanup_game(game_id)
            self._game_locks.pop(game_id, None)
            await self._heartbeat.stop_for_game(game_id)
            self._game_service.cleanup_game(game_id)
            if self._replay_collector:
                self._replay_collector.cleanup_game(game_id)

    @staticmethod
    def _remove_player_from_game(game: Game, connection_id: str, player: Player) -> None:
        """Remove a player from a game and clear their game association."""
        game.players.pop(connection_id, None)
        player.game_id = None
        player.seat = None

    async def _replace_with_bot(self, game: Game, player_name: str, seat: int) -> None:
        """
        Replace a disconnected human with a bot and process any pending bot actions.

        Must be called under the per-game lock (leave_game acquires it).
        Must be called BEFORE the is_empty cleanup check, and only when other
        humans remain in the game.
        """
        self._game_service.replace_player_with_bot(game.game_id, player_name)

        # cancel the disconnected player's timer to prevent stale callbacks
        player_timer = self._timer_manager.remove_timer(game.game_id, seat)
        if player_timer:
            player_timer.cancel()

        # process bot actions if the replaced player had a pending turn or call.
        # the caller (leave_game) already holds the game lock, so no separate
        # lock acquisition is needed here.
        events = await self._game_service.process_bot_actions_after_replacement(game.game_id, seat)
        if events:
            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)
            await self._close_connections_on_game_end(game, events)

    async def handle_game_action(
        self,
        connection: ConnectionProtocol,
        action: GameAction,
        data: dict[str, Any],
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            await self._send_error(connection, SessionErrorCode.NOT_IN_GAME, "You must join a game first")
            return

        game = self._games.get(player.game_id)
        if game is None:
            return

        game_id = player.game_id
        lock = self._get_game_lock(game_id)
        if lock is None:
            await self._send_error(connection, SessionErrorCode.GAME_NOT_STARTED, "Game has not started yet")
            return

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
            if player.seat is not None and not self._has_error_events(events):
                self._timer_manager.stop_player_timer(game_id, player.seat)
                # cancel meld timers for other players only when the prompt resolved
                if self._has_game_events(events):
                    self._timer_manager.cancel_other_timers(game_id, player.seat)

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
            await self._send_error(connection, SessionErrorCode.NOT_IN_GAME, "You must join a game first")
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
        self._heartbeat.record_ping(connection.connection_id)
        await connection.send_message(PongMessage().model_dump())

    async def _start_mahjong_game(self, game: Game) -> None:
        """
        Start the mahjong game when num_humans_needed players have joined.
        """
        game.started = True
        player_names = game.player_names
        events = await self._game_service.start_game(game.game_id, player_names, settings=game.settings)

        # if startup failed (e.g. unsupported settings), rollback and broadcast error
        if any(isinstance(e.data, ErrorEvent) for e in events):
            game.started = False
            await self._broadcast_events(game, events)
            return

        self._start_replay_collection(game.game_id)

        # assign seats to session players still connected after the await
        for player in game.players.values():
            seat = self._game_service.get_player_seat(game.game_id, player.name)
            if seat is not None:
                player.seat = seat

        # create per-player timers and lock for this game
        seats = [p.seat for p in game.players.values() if p.seat is not None]
        timer_config = TimerConfig.from_settings(game.settings)
        self._timer_manager.create_timers(game.game_id, seats, config=timer_config)
        self._game_locks[game.game_id] = asyncio.Lock()
        self._heartbeat.start_for_game(game.game_id, self.get_game)

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
                        player_timer = self._timer_manager.remove_timer(game.game_id, seat)
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
        """Broadcast events with target-based filtering using typed targets."""
        if self._replay_collector:
            self._replay_collector.collect_events(game.game_id, events)

        seat_to_player = {p.seat: p for p in game.players.values() if p.seat is not None}

        for event in events:
            message = service_event_payload(event)
            if isinstance(event.data, CallPromptEvent):
                message = shape_call_prompt_payload(message)

            if isinstance(event.target, BroadcastTarget):
                await self._broadcast_to_game(game, message)
            elif isinstance(event.target, SeatTarget):
                player = seat_to_player.get(event.target.seat)
                if player:
                    with contextlib.suppress(RuntimeError, OSError):
                        await player.connection.send_message(message)

    async def _broadcast_to_game(
        self,
        game: Game,
        message: dict[str, Any],
        exclude_connection_id: str | None = None,
    ) -> None:
        # snapshot to avoid RuntimeError if a concurrent leave_game mutates
        # game.players while we yield on send_message
        for player in list(game.players.values()):
            if player.connection_id != exclude_connection_id:
                # ignore connection errors, will be cleaned up on disconnect
                with contextlib.suppress(RuntimeError, OSError):
                    await player.connection.send_message(message)

    async def _maybe_start_timer(self, game: Game, events: list[ServiceEvent]) -> None:
        """Inspect events and delegate timer actions to TimerManager."""
        game_id = game.game_id

        # game ended -- cancel all timers
        if any(isinstance(event.data, GameEndedEvent) for event in events):
            self._timer_manager.cancel_all(game_id)
            return

        if not self._timer_manager.has_game(game_id):
            return

        # add round bonus to all player timers when a new round starts
        if any(isinstance(event.data, RoundStartedEvent) for event in events):
            self._timer_manager.add_round_bonus(game_id)

        # round end -- start round advance timers for human players
        if any(isinstance(event.data, RoundEndEvent) for event in events):
            self._timer_manager.start_round_advance_timers(game)
            return

        if self._start_turn_timer_from_events(game, events):
            return

        self._start_meld_timers_from_events(game, events)

    def _start_turn_timer_from_events(self, game: Game, events: list[ServiceEvent]) -> bool:
        """Start a turn timer if events contain a DrawEvent for a connected player."""
        for event in events:
            if isinstance(event.data, DrawEvent):
                seat = event.data.seat
                if self._get_player_at_seat(game, seat) is not None:
                    self._timer_manager.start_turn_timer(game.game_id, seat)
                    return True
        return False

    def _start_meld_timers_from_events(self, game: Game, events: list[ServiceEvent]) -> None:
        """Start meld timers for connected callers from per-seat CallPromptEvent wrappers."""
        for event in events:
            if isinstance(event.data, CallPromptEvent) and isinstance(event.target, SeatTarget):
                seat = event.target.seat
                if self._get_player_at_seat(game, seat) is not None:
                    self._timer_manager.start_meld_timer(game.game_id, seat)

    async def close_game_on_error(self, connection: ConnectionProtocol) -> None:
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

        Persists the replay before closing sockets. The WebSocket disconnect
        handlers will clean up session state (remove players, clean up empty
        game) when connections close.
        """
        if not any(isinstance(event.data, GameEndedEvent) for event in events):
            return
        if self._replay_collector:
            await self._replay_collector.save_and_cleanup(game.game_id)
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

    async def _handle_timeout(self, game_id: str, timeout_type: TimeoutType, seat: int) -> None:
        lock = self._get_game_lock(game_id)
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
                self._timer_manager.consume_bank(game_id, seat)

            events = await self._game_service.handle_timeout(game_id, player.name, timeout_type)
            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)
            await self._close_connections_on_game_end(game, events)
