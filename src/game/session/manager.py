import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from game.logic.enums import GameAction, MeldViewType, TimeoutType
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    DrawEvent,
    ErrorEvent,
    FuritenEvent,
    GameEndedEvent,
    MeldEvent,
    RoundEndEvent,
    RoundStartedEvent,
    SeatTarget,
)
from game.logic.exceptions import InvalidGameActionError
from game.logic.timer import TimerConfig
from game.messaging.event_payload import service_event_payload, shape_call_prompt_payload
from game.messaging.types import (
    ErrorMessage,
    GameLeftMessage,
    GameStartingMessage,
    PlayerJoinedMessage,
    PlayerLeftMessage,
    PlayerReadyChangedMessage,
    PongMessage,
    RoomJoinedMessage,
    RoomLeftMessage,
    SessionChatMessage,
    SessionErrorCode,
)
from game.session.heartbeat import HeartbeatMonitor
from game.session.models import Game, Player
from game.session.room import Room, RoomPlayer
from game.session.session_store import SessionStore
from game.session.timer_manager import TimerManager
from game.session.types import RoomInfo
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
        self._rooms: dict[str, Room] = {}  # room_id -> Room
        self._room_players: dict[str, RoomPlayer] = {}  # connection_id -> RoomPlayer
        self._room_locks: dict[str, asyncio.Lock] = {}  # room_id -> room transition/mutation lock
        self._session_store = SessionStore()
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

    def _start_replay_collection(self, game_id: str) -> None:
        """Start replay collection with the game seed (known after game_service.start_game)."""
        if self._replay_collector:
            seed = self._game_service.get_game_seed(game_id)
            if seed is not None:
                game_state = self._game_service.get_game_state(game_id)
                rng_version = game_state.rng_version if game_state is not None else ""
                self._replay_collector.start_game(game_id, seed, rng_version)

    async def _send_error(self, connection: ConnectionProtocol, code: SessionErrorCode, message: str) -> None:
        await connection.send_message(ErrorMessage(code=code, message=message).model_dump())

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
            self._session_store.remove_session(player.session_token)
            player.game_id = None
            player.seat = None
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
                self._session_store.mark_disconnected(player.session_token)
                self._remove_player_from_game(game, connection.connection_id, player)
                await self._notify_player_left(connection, game, player_name, notify_player=notify_player)
                # replace disconnected player with AI player (only if other players remain)
                if not game.is_empty and player_seat is not None:
                    await self._replace_with_ai_player(game, player_name, player_seat)
        else:
            # Two cases without a lock:
            # 1. Started game but lock not yet created (disconnect during _start_mahjong_game
            #    setup, before lock/timer infrastructure is ready). _start_mahjong_game
            #    handles AI player replacement for players who left during startup.
            # 2. Pre-start game: no concurrent action/timeout paths.
            if game.started:
                self._session_store.mark_disconnected(player.session_token)
            else:
                self._session_store.remove_session(player.session_token)
            self._remove_player_from_game(game, connection.connection_id, player)
            await self._notify_player_left(connection, game, player_name, notify_player=notify_player)

        await self._cleanup_empty_game(game_id, game)

    @staticmethod
    def _remove_player_from_game(game: Game, connection_id: str, player: Player) -> None:
        """Remove a player from a game and clear their game association."""
        game.players.pop(connection_id, None)
        player.game_id = None
        player.seat = None

    async def _notify_player_left(
        self,
        connection: ConnectionProtocol,
        game: Game,
        player_name: str,
        *,
        notify_player: bool,
    ) -> None:
        """Send leave notification to the player and broadcast departure to the game."""
        if notify_player:
            with contextlib.suppress(RuntimeError, OSError):
                await connection.send_message(GameLeftMessage().model_dump())
        await self._broadcast_to_game(
            game=game,
            message=PlayerLeftMessage(player_name=player_name).model_dump(),
        )

    async def _cleanup_empty_game(self, game_id: str, game: Game) -> None:
        """Clean up an empty game: remove from registry, stop timers/heartbeat, cleanup service state."""
        if game.is_empty and self._games.pop(game_id, None) is not None:
            logger.info(f"game {game_id} is empty, cleaning up")
            self._session_store.cleanup_game(game_id)
            self._timer_manager.cleanup_game(game_id)
            self._game_locks.pop(game_id, None)
            await self._heartbeat.stop_for_game(game_id)
            self._game_service.cleanup_game(game_id)
            if self._replay_collector:
                self._replay_collector.cleanup_game(game_id)

    async def _replace_with_ai_player(self, game: Game, player_name: str, seat: int) -> None:
        """
        Replace a disconnected player with an AI player and process any pending AI player actions.

        Must be called under the per-game lock (leave_game acquires it).
        Must be called BEFORE the is_empty cleanup check, and only when other
        players remain in the game.
        """
        self._game_service.replace_with_ai_player(game.game_id, player_name)

        # cancel the disconnected player's timer to prevent stale callbacks
        player_timer = self._timer_manager.remove_timer(game.game_id, seat)
        if player_timer:
            player_timer.cancel()

        # process AI player actions if the replaced player had a pending turn or call.
        # the caller (leave_game) already holds the game lock, so no separate
        # lock acquisition is needed here.
        events = await self._game_service.process_ai_player_actions_after_replacement(game.game_id, seat)
        if events:
            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)
            await self._close_connections_on_game_end(game, events)

    async def _handle_invalid_action(
        self,
        game: Game,
        connection: ConnectionProtocol,
        player: Player,
        error: InvalidGameActionError,
    ) -> None:
        """Handle a provably invalid game action: log, disconnect, replace with AI player.

        Must be called under the per-game lock.
        Connection close and empty-game cleanup happen OUTSIDE the lock (by the caller).
        """
        game_id = game.game_id
        player_name = player.name
        player_seat = player.seat

        logger.warning(
            f"invalid game action: game={game_id} user_id={connection.connection_id} player={player_name} "
            f"seat={error.seat} action={error.action} reason={error.reason}"
        )

        self._session_store.mark_disconnected(player.session_token)
        self._remove_player_from_game(game, connection.connection_id, player)

        await self._broadcast_to_game(
            game=game,
            message=PlayerLeftMessage(player_name=player_name).model_dump(),
        )

        if not game.is_empty and player_seat is not None:
            await self._replace_with_ai_player(game, player_name, player_seat)

    async def _process_successful_action(
        self, game: Game, game_id: str, player: Player, events: list[ServiceEvent]
    ) -> None:
        """Handle timer management and broadcasting after a successful game action."""
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

    async def _process_invalid_action(
        self, game: Game, game_id: str, error: InvalidGameActionError
    ) -> ConnectionProtocol | None:
        """Handle InvalidGameActionError under the lock.

        Returns the offender connection for post-lock close, or None if the offending seat
        has no connected player (e.g. AI player seat).
        """
        # resolve offender by seat from exception (critical for resolution-triggered errors)
        offender_player = self._get_player_at_seat(game, error.seat)
        if offender_player is None:
            # offending seat has no connected player (AI player seat) — log and skip disconnect
            logger.warning(
                f"game {game_id}: InvalidGameActionError at seat {error.seat} "
                f"but no player found (likely an AI player seat), skipping disconnect"
            )
            return None
        offender_connection = offender_player.connection
        try:
            await self._handle_invalid_action(game, offender_connection, offender_player, error)
        except Exception:
            logger.exception(
                f"error during invalid action handling for game {game_id}, "
                f"player already removed, continuing with disconnect"
            )
        return offender_connection

    async def _close_offender_and_cleanup(
        self, offender_connection: ConnectionProtocol | None, game_id: str, game: Game
    ) -> None:
        """Close the offender's connection and clean up the game if empty.

        Called OUTSIDE the per-game lock to avoid deadlock risk from connection.close()
        triggering WebSocket disconnect handler.
        """
        if offender_connection is None:
            return
        with contextlib.suppress(RuntimeError, OSError):
            await offender_connection.close(code=1008, reason="invalid_game_action")
        await self._cleanup_empty_game(game_id, game)

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

        offender_connection: ConnectionProtocol | None = None
        async with lock:
            try:
                events = await self._game_service.handle_action(
                    game_id=game_id,
                    player_name=player.name,
                    action=action,
                    data=data,
                )
            except InvalidGameActionError as e:
                offender_connection = await self._process_invalid_action(game, game_id, e)
            else:
                await self._process_successful_action(game, game_id, player, events)

        await self._close_offender_and_cleanup(offender_connection, game_id, game)

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

    # --- Room management ---

    def create_room(self, room_id: str, num_ai_players: int = 3) -> Room:
        """Create a room for pre-game gathering."""
        if self._log_dir:
            rotate_log_file(self._log_dir)
        room = Room(room_id=room_id, num_ai_players=num_ai_players)
        self._rooms[room_id] = room
        self._room_locks[room_id] = asyncio.Lock()
        logger.info(f"room created: {room_id} num_ai_players={num_ai_players}")
        return room

    def get_room(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    def _get_room_lock(self, room_id: str) -> asyncio.Lock:
        lock = self._room_locks.get(room_id)
        if lock is None:
            lock = asyncio.Lock()
            self._room_locks[room_id] = lock
        return lock

    def is_in_room(self, connection_id: str) -> bool:
        return connection_id in self._room_players

    def is_in_active_game(self, connection_id: str) -> bool:
        player = self._players.get(connection_id)
        return player is not None and player.game_id is not None

    @property
    def room_count(self) -> int:
        return len(self._rooms)

    def get_rooms_info(self) -> list[RoomInfo]:
        """Return info about all active rooms for the lobby list."""
        return [
            RoomInfo(
                room_id=room.room_id,
                player_count=room.player_count,
                players_needed=room.players_needed,
                total_seats=room.total_seats,
                num_ai_players=room.num_ai_players,
                players=room.player_names,
            )
            for room in self._rooms.values()
        ]

    async def join_room(
        self, connection: ConnectionProtocol, room_id: str, player_name: str, session_token: str
    ) -> None:
        """Handle a player joining a room."""
        if self.is_in_active_game(connection.connection_id):
            await self._send_error(
                connection,
                SessionErrorCode.ALREADY_IN_GAME,
                "You must leave your current game first",
            )
            return

        existing = self._room_players.get(connection.connection_id)
        if existing:
            await self._send_error(
                connection,
                SessionErrorCode.ALREADY_IN_ROOM,
                "You must leave your current room first",
            )
            return

        room = self._rooms.get(room_id)
        if room is None:
            await self._send_error(connection, SessionErrorCode.ROOM_NOT_FOUND, "Room does not exist")
            return

        if room.transitioning:
            await self._send_error(
                connection,
                SessionErrorCode.ROOM_TRANSITIONING,
                "Room is starting a game",
            )
            return

        if room.is_full:
            await self._send_error(connection, SessionErrorCode.ROOM_FULL, "Room is full")
            return

        if player_name in room.player_names:
            await self._send_error(
                connection,
                SessionErrorCode.NAME_TAKEN,
                "That name is already taken in this room",
            )
            return

        room_player = RoomPlayer(
            connection=connection, name=player_name, room_id=room_id, session_token=session_token
        )
        self._room_players[connection.connection_id] = room_player
        room.players[connection.connection_id] = room_player

        # First player becomes the host
        if room.host_connection_id is None:
            room.host_connection_id = connection.connection_id
            self._heartbeat.start_for_room(room.room_id, self.get_room)

        await connection.send_message(
            RoomJoinedMessage(
                room_id=room_id,
                session_token=session_token,
                players=room.get_player_info(),
                num_ai_players=room.num_ai_players,
            ).model_dump()
        )

        await self._broadcast_to_room(
            room=room,
            message=PlayerJoinedMessage(player_name=player_name).model_dump(),
            exclude_connection_id=connection.connection_id,
        )

    async def leave_room(self, connection: ConnectionProtocol, *, notify_player: bool = True) -> None:
        """Handle a player leaving a room."""
        room_player = self._room_players.get(connection.connection_id)
        if room_player is None:
            return

        room_id = room_player.room_id
        room_lock = self._get_room_lock(room_id)
        async with room_lock:
            room = self._rooms.get(room_id)
            if room is None:
                self._room_players.pop(connection.connection_id, None)
                self._room_locks.pop(room_id, None)
                return

            player_name = room_player.name

            room.players.pop(connection.connection_id, None)
            self._room_players.pop(connection.connection_id, None)

            if room.host_connection_id == connection.connection_id:
                room.host_connection_id = next(iter(room.players), None)

            should_cleanup = room.is_empty
            if should_cleanup:
                self._rooms.pop(room_id, None)
                self._room_locks.pop(room_id, None)

        if notify_player:
            with contextlib.suppress(RuntimeError, OSError):
                await connection.send_message(RoomLeftMessage().model_dump())

        if not should_cleanup:
            await self._broadcast_to_room(
                room=room,
                message=PlayerLeftMessage(player_name=player_name).model_dump(),
            )

        if should_cleanup:
            await self._heartbeat.stop_for_room(room_id)

    async def set_ready(self, connection: ConnectionProtocol, *, ready: bool) -> None:
        """Toggle a player's ready state. Start game if all ready."""
        room_player = self._room_players.get(connection.connection_id)
        if room_player is None:
            if self.is_in_active_game(connection.connection_id):
                return
            await self._send_error(
                connection,
                SessionErrorCode.NOT_IN_ROOM,
                "You must join a room first",
            )
            return

        room_id = room_player.room_id
        room_lock = self._get_room_lock(room_id)
        should_transition = False
        async with room_lock:
            room = self._rooms.get(room_id)
            if room is None or room.transitioning:
                return

            room_player.ready = ready
            if room.all_ready and not room.transitioning:
                room.transitioning = True
                should_transition = True

        await self._broadcast_to_room(
            room=room,
            message=PlayerReadyChangedMessage(
                player_name=room_player.name,
                ready=ready,
            ).model_dump(),
        )

        if should_transition:
            await self._transition_room_to_game(room_id)

    async def _transition_room_to_game(self, room_id: str) -> None:
        """Transition a room to a running game when all players are ready."""
        room_lock = self._get_room_lock(room_id)
        async with room_lock:
            room = self._rooms.get(room_id)
            if room is None or not room.transitioning:
                return

            # Re-validate after re-acquiring the lock: a player may have left
            # between set_ready releasing the lock and this acquisition.
            if not room.all_ready:
                room.transitioning = False
                return

            room_players = list(room.players.values())
            game = Game(game_id=room.room_id, num_ai_players=room.num_ai_players, settings=room.settings)
            self._games[room.room_id] = game

            for rp in room_players:
                session = self._session_store.create_session(rp.name, room.room_id, token=rp.session_token)
                player = Player(
                    connection=rp.connection,
                    name=rp.name,
                    session_token=session.session_token,
                    game_id=room.room_id,
                )
                self._players[rp.connection_id] = player
                game.players[rp.connection_id] = player
                self._room_players.pop(rp.connection_id, None)

            self._rooms.pop(room.room_id, None)
            self._room_locks.pop(room.room_id, None)

        await self._heartbeat.stop_for_room(room_id)

        message = GameStartingMessage().model_dump()
        for rp in room_players:
            with contextlib.suppress(RuntimeError, OSError):
                await rp.connection.send_message(message)

        # Log rotation already happened in create_room.
        await self._start_mahjong_game(game)

    async def _broadcast_to_room(
        self,
        room: Room,
        message: dict[str, Any],
        exclude_connection_id: str | None = None,
    ) -> None:
        """Broadcast a message to all players in a room."""
        await self._broadcast_to_players(room.players, message, exclude_connection_id)

    async def broadcast_room_chat(self, connection: ConnectionProtocol, text: str) -> None:
        """Broadcast a chat message to all players in the same room."""
        room_player = self._room_players.get(connection.connection_id)
        if room_player is None:
            await self._send_error(
                connection,
                SessionErrorCode.NOT_IN_ROOM,
                "You must join a room first",
            )
            return

        room = self._rooms.get(room_player.room_id)
        if room is None:
            return

        await self._broadcast_to_room(
            room=room,
            message=SessionChatMessage(
                player_name=room_player.name,
                text=text,
            ).model_dump(),
        )

    def _is_game_alive(self, game: Game) -> bool:
        """Check if a game is still tracked and has connected players."""
        return self._games.get(game.game_id) is game and not game.is_empty

    async def _start_mahjong_game(self, game: Game) -> None:
        """
        Start the mahjong game when all required players are ready.
        """
        # Guard: if all players disconnected during the transition window
        # (between GameStartingMessage and this call), leave_game may have
        # already cleaned the game out of _games. Starting a game that is
        # no longer tracked would leak locks, heartbeat tasks, and service state.
        if not self._is_game_alive(game):
            return

        game.started = True
        player_names = game.player_names
        events = await self._game_service.start_game(game.game_id, player_names, settings=game.settings)

        # if startup failed (e.g. unsupported settings), rollback and broadcast error
        if any(isinstance(e.data, ErrorEvent) for e in events):
            game.started = False
            await self._broadcast_events(game, events)
            return

        # Second liveness check: if all players disconnected during the
        # start_game await, leave_game may have cleaned the game from _games.
        # Clean up the service state that start_game just created and bail out.
        if not self._is_game_alive(game):
            self._game_service.cleanup_game(game.game_id)
            return

        self._start_replay_collection(game.game_id)

        # assign seats to session players still connected after the await
        for player in game.players.values():
            seat = self._game_service.get_player_seat(game.game_id, player.name)
            if seat is not None:
                player.seat = seat
                self._session_store.bind_seat(player.session_token, seat)

        # create per-player timers and lock for this game
        seats = [p.seat for p in game.players.values() if p.seat is not None]
        timer_config = TimerConfig.from_settings(game.settings)
        self._timer_manager.create_timers(game.game_id, seats, config=timer_config)
        self._game_locks[game.game_id] = asyncio.Lock()
        self._heartbeat.start_for_game(game.game_id, self.get_game)

        async with self._game_locks[game.game_id]:
            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)
            await self._replace_disconnected_players(game, player_names)

    async def _replace_disconnected_players(self, game: Game, original_player_names: list[str]) -> None:
        """Replace players who disconnected during start_game or subsequent broadcasts.

        Called under the per-game lock. Players who left before seats/locks
        were set up could not be replaced by leave_game, so handle them here.
        """
        connected_names = set(game.player_names)
        for name in original_player_names:
            if name not in connected_names and not game.is_empty:
                seat = self._game_service.get_player_seat(game.game_id, name)
                if seat is not None:
                    self._game_service.replace_with_ai_player(game.game_id, name)
                    player_timer = self._timer_manager.remove_timer(game.game_id, seat)
                    if player_timer:
                        player_timer.cancel()
                    ai_player_events = await self._game_service.process_ai_player_actions_after_replacement(
                        game.game_id, seat
                    )
                    if ai_player_events:
                        await self._broadcast_events(game, ai_player_events)
                        await self._maybe_start_timer(game, ai_player_events)
                        await self._close_connections_on_game_end(game, ai_player_events)

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
        await self._broadcast_to_players(game.players, message, exclude_connection_id)

    async def _broadcast_to_players(
        self,
        players: dict[str, Any],
        message: dict[str, Any],
        exclude_connection_id: str | None = None,
    ) -> None:
        """Broadcast a message to all players in a dict, skipping one if excluded.

        Snapshots the dict values to avoid RuntimeError if a concurrent
        leave mutates the dict while we yield on send_message.
        """
        for player in list(players.values()):
            if player.connection_id != exclude_connection_id:
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

        # round end -- start round advance timers for players
        if any(isinstance(event.data, RoundEndEvent) for event in events):
            self._timer_manager.start_round_advance_timers(game)
            return

        if self._start_turn_timer_from_events(game, events):
            return

        self._start_meld_timers_from_events(game, events)

    _PON_CHI_MELD_TYPES = frozenset({MeldViewType.PON, MeldViewType.CHI})

    def _start_turn_timer_from_events(self, game: Game, events: list[ServiceEvent]) -> bool:
        """Start a turn timer if events contain a DrawEvent or a pon/chi MeldEvent."""
        for event in events:
            if isinstance(event.data, DrawEvent):
                seat = event.data.seat
                if self._get_player_at_seat(game, seat) is not None:
                    self._timer_manager.start_turn_timer(game.game_id, seat)
                    return True
            elif isinstance(event.data, MeldEvent) and event.data.meld_type in self._PON_CHI_MELD_TYPES:
                seat = event.data.caller_seat
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

        offender_connection: ConnectionProtocol | None = None
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

            try:
                events = await self._game_service.handle_timeout(game_id, player.name, timeout_type)
            except InvalidGameActionError as e:
                offender_connection = await self._process_invalid_action(game, game_id, e)
            else:
                await self._broadcast_events(game, events)
                await self._maybe_start_timer(game, events)
                await self._close_connections_on_game_end(game, events)

        await self._close_offender_and_cleanup(offender_connection, game_id, game)
