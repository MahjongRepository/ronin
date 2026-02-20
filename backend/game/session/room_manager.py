"""Room lifecycle management: creation, joining, readiness, and transition to game."""

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

from game.messaging.types import (
    ErrorMessage,
    PlayerJoinedMessage,
    PlayerLeftMessage,
    PlayerReadyChangedMessage,
    RoomJoinedMessage,
    RoomLeftMessage,
    SessionChatMessage,
    SessionErrorCode,
)
from game.session.broadcast import broadcast_to_players
from game.session.room import Room, RoomPlayer
from game.session.types import RoomInfo
from shared.logging import rotate_log_file

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from game.logic.settings import GameSettings
    from game.messaging.protocol import ConnectionProtocol
    from game.session.heartbeat import HeartbeatMonitor

logger = logging.getLogger(__name__)

_ROOM_REAPER_INTERVAL = 30  # seconds between reaper checks


class RoomManager:
    """Manage room lifecycle: creation, join/leave, readiness, and transition.

    Owns all room state (_rooms, _room_players, _room_locks). Uses a callback
    pattern for game transition (like TimerManager.on_timeout) to bridge room
    completion to game creation without knowing about game-layer concerns.
    """

    def __init__(
        self,
        *,
        heartbeat: HeartbeatMonitor,
        on_transition: Callable[
            [str, list[RoomPlayer], int, GameSettings],
            Coroutine[Any, Any, None],
        ],
        is_in_active_game: Callable[[str], bool],
        log_dir: str | None = None,
        room_ttl_seconds: int = 0,
    ) -> None:
        self._heartbeat = heartbeat
        self._on_transition = on_transition
        self._is_in_active_game = is_in_active_game
        self._log_dir = log_dir
        self._room_ttl_seconds = room_ttl_seconds
        self._rooms: dict[str, Room] = {}
        self._room_players: dict[str, RoomPlayer] = {}  # connection_id -> RoomPlayer
        self._room_locks: dict[str, asyncio.Lock] = {}
        self._room_reaper_task: asyncio.Task[None] | None = None

    # --- Public API ---

    def create_room(self, room_id: str, num_ai_players: int = 3) -> Room:
        """Create a room for pre-game gathering."""
        if self._log_dir:
            rotate_log_file(self._log_dir, name=room_id)
        room = Room(room_id=room_id, num_ai_players=num_ai_players)
        self._rooms[room_id] = room
        self._room_locks[room_id] = asyncio.Lock()
        logger.info("room created, num_ai_players=%d", num_ai_players)
        return room

    def get_room(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    def is_in_room(self, connection_id: str) -> bool:
        return connection_id in self._room_players

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
        self,
        connection: ConnectionProtocol,
        room_id: str,
        player_name: str,
        user_id: str = "",
        session_token: str = "",
    ) -> None:
        """Handle a player joining a room."""
        if self._is_in_active_game(connection.connection_id):
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

        room_lock = self._room_locks.get(room_id)
        if room_lock is None:
            await self._send_error(connection, SessionErrorCode.ROOM_NOT_FOUND, "Room does not exist")
            return

        start_heartbeat = False
        async with room_lock:
            if await self._validate_join_room(room_id, player_name, connection):
                return

            room = self._rooms[room_id]
            room_player = RoomPlayer(
                connection=connection,
                name=player_name,
                room_id=room_id,
                session_token=session_token,
                user_id=user_id,
            )
            self._room_players[connection.connection_id] = room_player
            room.players[connection.connection_id] = room_player

            if room.host_connection_id is None:
                room.host_connection_id = connection.connection_id
                start_heartbeat = True

            # Capture snapshot inside the lock for messages sent outside
            player_info = room.get_player_info()
            num_ai_players = room.num_ai_players

        if start_heartbeat:
            self._heartbeat.start_for_room(room.room_id, self.get_room)

        await connection.send_message(
            RoomJoinedMessage(
                room_id=room_id,
                player_name=player_name,
                players=player_info,
                num_ai_players=num_ai_players,
            ).model_dump(),
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
        player_name = room_player.name
        room_lock = self._room_locks.get(room_id)
        should_cleanup = False
        if room_lock is None:
            # Room already cleaned up; just remove the stale room_player reference.
            self._room_players.pop(connection.connection_id, None)
            return

        async with room_lock:
            room = self._rooms.get(room_id)
            if room is None:
                self._room_players.pop(connection.connection_id, None)
                return

            room.players.pop(connection.connection_id, None)
            self._room_players.pop(connection.connection_id, None)

            if room.host_connection_id == connection.connection_id:
                room.host_connection_id = next(iter(room.players), None)

            should_cleanup = room.is_empty
            if should_cleanup:
                self._rooms.pop(room_id, None)

        # Clean up the lock outside the async with block to avoid
        # deleting the lock while still holding it.
        if should_cleanup:
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
            if self._is_in_active_game(connection.connection_id):
                return
            await self._send_error(
                connection,
                SessionErrorCode.NOT_IN_ROOM,
                "You must join a room first",
            )
            return

        room_id = room_player.room_id
        room_lock = self._room_locks.get(room_id)
        if room_lock is None:
            return
        should_transition = False
        async with room_lock:
            room = self._rooms.get(room_id)
            if room is None or room.transitioning:
                return

            room_player.ready = ready
            if room.all_ready:
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

    # --- Room reaper ---

    def start_room_reaper(self) -> None:
        """Start the periodic room reaper task. Idempotent."""
        if self._room_ttl_seconds <= 0:
            return
        if self._room_reaper_task is not None and not self._room_reaper_task.done():
            return
        self._room_reaper_task = asyncio.create_task(self._room_reaper_loop())

    async def stop_room_reaper(self) -> None:
        """Stop the room reaper task."""
        if self._room_reaper_task is not None:
            self._room_reaper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._room_reaper_task
            self._room_reaper_task = None

    async def _room_reaper_loop(self) -> None:
        """Periodically check for and close expired rooms."""
        while True:
            await asyncio.sleep(_ROOM_REAPER_INTERVAL)
            try:
                await self._reap_expired_rooms()
            except Exception:
                logger.exception("room reaper encountered an error")

    async def _reap_expired_rooms(self) -> None:
        """Close all player connections in rooms that have exceeded the TTL.

        For each expired room, acquires the room lock and re-validates the
        expiry and transition state before acting. Non-empty rooms are removed
        from _rooms under the lock (preventing new joins) before closing
        connections. Empty rooms are cleaned up directly.
        """
        now = time.monotonic()
        expired_candidates = [
            room.room_id
            for room in list(self._rooms.values())
            if now - room.created_at > self._room_ttl_seconds and not room.transitioning
        ]
        for room_id in expired_candidates:
            room_lock = self._room_locks.get(room_id)
            if room_lock is None:
                continue

            should_cleanup_lock = False
            players_to_close: list[RoomPlayer] = []

            async with room_lock:
                room = self._rooms.get(room_id)
                if room is None or room.transitioning:
                    continue

                logger.info(
                    "room %s expired (age %.0fs > TTL %ds), closing",
                    room.room_id,
                    now - room.created_at,
                    self._room_ttl_seconds,
                )

                if room.is_empty:
                    self._rooms.pop(room.room_id, None)
                    should_cleanup_lock = True
                else:
                    # Snapshot players and remove room atomically under the lock
                    # to prevent new joins while we close connections.
                    players_to_close = list(room.players.values())
                    for rp in players_to_close:
                        self._room_players.pop(rp.connection_id, None)
                    self._rooms.pop(room.room_id, None)
                    should_cleanup_lock = True

            # Clean up the lock outside the async with block.
            if should_cleanup_lock:
                self._room_locks.pop(room_id, None)

            if players_to_close:
                await self._heartbeat.stop_for_room(room_id)
                for player in players_to_close:
                    with contextlib.suppress(RuntimeError, OSError):
                        await player.connection.close(code=1000, reason="room_expired")

    # --- Internal helpers ---

    async def _validate_join_room(
        self,
        room_id: str,
        player_name: str,
        connection: ConnectionProtocol,
    ) -> bool:
        """Validate room join preconditions under the room lock.

        Returns True if validation failed (error already sent), False if the join is allowed.
        """
        room = self._rooms.get(room_id)
        if room is None:
            await self._send_error(connection, SessionErrorCode.ROOM_NOT_FOUND, "Room does not exist")
            return True

        if room.transitioning:
            await self._send_error(
                connection,
                SessionErrorCode.ROOM_TRANSITIONING,
                "Room is starting a game",
            )
            return True

        if room.is_full:
            await self._send_error(connection, SessionErrorCode.ROOM_FULL, "Room is full")
            return True

        if player_name in room.player_names:
            await self._send_error(
                connection,
                SessionErrorCode.NAME_TAKEN,
                "That name is already taken in this room",
            )
            return True

        return False

    async def _transition_room_to_game(self, room_id: str) -> None:
        """Transition a room to a running game when all players are ready."""
        room_lock = self._room_locks.get(room_id)
        if room_lock is None:
            return
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
            settings = room.settings
            num_ai_players = room.num_ai_players

            # Clean up room state before transition
            for rp in room_players:
                self._room_players.pop(rp.connection_id, None)

            self._rooms.pop(room.room_id, None)

        # Clean up the lock outside the async with block.
        self._room_locks.pop(room_id, None)
        await self._heartbeat.stop_for_room(room_id)

        # Delegate game creation to the callback (SessionManager handles game-layer concerns)
        await self._on_transition(room_id, room_players, num_ai_players, settings)

    async def _broadcast_to_room(
        self,
        room: Room,
        message: dict[str, Any],
        exclude_connection_id: str | None = None,
    ) -> None:
        """Broadcast a message to all players in a room."""
        await broadcast_to_players(room.players, message, exclude_connection_id)

    @staticmethod
    async def _send_error(connection: ConnectionProtocol, code: SessionErrorCode, message: str) -> None:
        await connection.send_message(ErrorMessage(code=code, message=message).model_dump())
