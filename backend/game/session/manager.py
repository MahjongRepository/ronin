import asyncio
import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from game.logic.enums import GameAction, MeldViewType, RoundPhase, TimeoutType
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
    PlayerLeftMessage,
    PlayerReconnectedMessage,
    PongMessage,
    SessionChatMessage,
    SessionErrorCode,
    SessionMessageType,
)
from game.session.broadcast import broadcast_to_players
from game.session.heartbeat import HeartbeatMonitor
from game.session.models import Game, Player, SessionData
from game.session.room_manager import RoomManager
from game.session.session_store import SessionStore
from game.session.timer_manager import TimerManager
from shared.dal.models import PlayedGame

if TYPE_CHECKING:
    from game.logic.events import ServiceEvent
    from game.logic.service import GameService
    from game.logic.settings import GameSettings
    from game.messaging.protocol import ConnectionProtocol
    from game.session.replay_collector import ReplayCollector
    from game.session.room import Room, RoomPlayer
    from game.session.types import RoomInfo
    from shared.dal.game_repository import GameRepository

logger = structlog.get_logger()


class SessionManager:
    def __init__(
        self,
        game_service: GameService,
        log_dir: str | None = None,
        replay_collector: ReplayCollector | None = None,
        room_ttl_seconds: int = 0,
        game_repository: GameRepository | None = None,
    ) -> None:
        self._game_service = game_service
        self._game_repository = game_repository
        self._log_dir = log_dir
        self._replay_collector = replay_collector
        self._connections: dict[str, ConnectionProtocol] = {}
        self._players: dict[str, Player] = {}  # connection_id -> Player
        self._games: dict[str, Game] = {}  # game_id -> Game
        self._session_store = SessionStore()
        self._timer_manager = TimerManager(on_timeout=self._handle_timeout)
        self._game_locks: dict[str, asyncio.Lock] = {}  # game_id -> Lock
        self._heartbeat = HeartbeatMonitor()
        self._room_manager = RoomManager(
            heartbeat=self._heartbeat,
            on_transition=self._handle_room_transition,
            is_in_active_game=self.is_in_active_game,
            log_dir=log_dir,
            room_ttl_seconds=room_ttl_seconds,
        )

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

    async def _record_game_start(self, game: Game) -> None:
        """Best-effort persist game start to the game repository."""
        if self._game_repository is None:
            return
        player_ids = [p.user_id for p in game.players.values() if p.user_id]
        played_game = PlayedGame(
            game_id=game.game_id,
            started_at=datetime.now(UTC),
            player_ids=player_ids,
        )
        try:
            await self._game_repository.create_game(played_game)
        except Exception:
            logger.exception("failed to persist game start")

    async def _record_game_finish(self, game_id: str, end_reason: str) -> None:
        """Best-effort persist game end to the game repository."""
        if self._game_repository is None:
            return
        try:
            await self._game_repository.finish_game(
                game_id,
                ended_at=datetime.now(UTC),
                end_reason=end_reason,
            )
        except Exception:
            logger.exception("failed to persist game end")

    async def _send_error(self, connection: ConnectionProtocol, code: SessionErrorCode, message: str) -> None:
        logger.warning("session error sent to client", error_code=code.value, error_message=message)
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
        logger.info("player left game")

        lock = self._get_game_lock(game_id) if game.started else None

        if lock is not None:
            # started game: guard all state mutation under the per-game lock
            # to prevent races with handle_game_action and timeout callbacks
            ai_events: list[ServiceEvent] = []
            async with lock:
                self._session_store.mark_disconnected(player.session_token)
                self._remove_player_from_game(game, connection.connection_id, player)
                await self._notify_player_left(connection, game, player_name, notify_player=notify_player)
                # replace disconnected player with AI player (only if other players remain)
                if not game.is_empty and player_seat is not None:
                    ai_events = await self._replace_with_ai_player(game, player_name, player_seat, player.session_token)
            # Close connections outside the lock if AI replacement ended the game
            if self._has_game_ended(ai_events):
                await self._close_connections_on_game_end(game, ai_events)
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
            logger.info("game is empty, cleaning up")
            if game.started and not game.ended:
                await self._record_game_finish(game_id, "abandoned")
            self._session_store.cleanup_game(game_id)
            self._timer_manager.cleanup_game(game_id)
            self._game_locks.pop(game_id, None)
            await self._heartbeat.stop_for_game(game_id)
            self._game_service.cleanup_game(game_id)
            if self._replay_collector:
                self._replay_collector.cleanup_game(game_id)

    async def _replace_with_ai_player(
        self,
        game: Game,
        player_name: str,
        seat: int,
        session_token: str | None = None,
    ) -> list[ServiceEvent]:
        """
        Replace a disconnected player with an AI player and process any pending AI player actions.

        Must be called under the per-game lock (leave_game acquires it).
        Must be called BEFORE the is_empty cleanup check, and only when other
        players remain in the game.

        Returns the events produced by AI player actions (caller handles game-end
        connection closing outside the lock).
        """
        self._game_service.replace_with_ai_player(game.game_id, player_name)

        # stop (not cancel) the timer to deduct elapsed bank time, then save remaining bank
        player_timer = self._timer_manager.remove_timer(game.game_id, seat)
        if player_timer:
            player_timer.stop()
            if session_token is not None:
                session = self._session_store.get_session(session_token)
                if session is not None:
                    session.remaining_bank_seconds = player_timer.bank_seconds

        # process AI player actions if the replaced player had a pending turn or call.
        # the caller (leave_game) already holds the game lock, so no separate
        # lock acquisition is needed here.
        events = await self._game_service.process_ai_player_actions_after_replacement(game.game_id, seat)
        if events:
            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)
        return events

    async def _handle_invalid_action(
        self,
        game: Game,
        connection: ConnectionProtocol,
        player: Player,
        error: InvalidGameActionError,
    ) -> list[ServiceEvent]:
        """Handle a provably invalid game action: log, disconnect, replace with AI player.

        Must be called under the per-game lock.
        Connection close and empty-game cleanup happen OUTSIDE the lock (by the caller).
        Returns AI replacement events (caller handles game-end connection closing outside the lock).
        """
        player_name = player.name
        player_seat = player.seat

        logger.warning("invalid game action", action=error.action, reason=error.reason)

        self._session_store.mark_disconnected(player.session_token)
        self._remove_player_from_game(game, connection.connection_id, player)

        await self._broadcast_to_game(
            game=game,
            message=PlayerLeftMessage(player_name=player_name).model_dump(),
        )

        if not game.is_empty and player_seat is not None:
            return await self._replace_with_ai_player(game, player_name, player_seat, player.session_token)
        return []

    async def _process_successful_action(
        self,
        game: Game,
        game_id: str,
        player: Player,
        events: list[ServiceEvent],
    ) -> bool:
        """Handle timer management and broadcasting after a successful game action.

        Returns True if the game ended (caller must close connections outside the lock).
        """
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
        return self._has_game_ended(events)

    async def _process_invalid_action(
        self,
        game: Game,
        error: InvalidGameActionError,
    ) -> tuple[ConnectionProtocol | None, list[ServiceEvent]]:
        """Handle InvalidGameActionError under the lock.

        Returns (offender_connection, ai_events). The offender connection is closed
        outside the lock by the caller. ai_events may contain a GameEndedEvent
        that requires closing all connections outside the lock.
        """
        # resolve offender by seat from exception (critical for resolution-triggered errors)
        offender_player = self._get_player_at_seat(game, error.seat)
        if offender_player is None:
            # offending seat has no connected player (AI player seat) — log and skip disconnect
            logger.warning("invalid action at AI player seat, skipping disconnect", error_seat=error.seat)
            return None, []
        offender_connection = offender_player.connection
        ai_events: list[ServiceEvent] = []
        try:
            ai_events = await self._handle_invalid_action(game, offender_connection, offender_player, error)
        except (RuntimeError, OSError, ConnectionError, ValueError, InvalidGameActionError):  # fmt: skip
            logger.exception("error during invalid action handling, player already removed, continuing with disconnect")
        return offender_connection, ai_events

    async def _close_offender_and_cleanup(
        self,
        offender_connection: ConnectionProtocol | None,
        game_id: str,
        game: Game,
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
        structlog.contextvars.bind_contextvars(seat=player.seat)
        lock = self._get_game_lock(game_id)
        if lock is None:
            await self._send_error(connection, SessionErrorCode.GAME_NOT_STARTED, "Game has not started yet")
            return

        offender_connection: ConnectionProtocol | None = None
        game_ended = False
        game_end_events: list[ServiceEvent] = []
        async with lock:
            try:
                events = await self._game_service.handle_action(
                    game_id=game_id,
                    player_name=player.name,
                    action=action,
                    data=data,
                )
            except InvalidGameActionError as e:
                offender_connection, ai_events = await self._process_invalid_action(game, e)
                if self._has_game_ended(ai_events):
                    game_end_events = ai_events
            else:
                game_ended = await self._process_successful_action(game, game_id, player, events)
                if game_ended:
                    game_end_events = events

        # Close connections outside the lock to avoid deadlock risk from
        # connection.close() triggering the WebSocket disconnect handler
        # which calls leave_game (which also acquires the per-game lock).
        if game_end_events:
            await self._close_connections_on_game_end(game, game_end_events)
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

    # --- Reconnection ---

    async def reconnect(
        self,
        connection: ConnectionProtocol,
        room_id: str,
        session_token: str,
    ) -> None:
        """Handle a player reconnecting to an active game."""
        result = await self._validate_reconnect(connection, room_id, session_token)
        if result is None:
            return

        session, game, lock, seat = result
        game_id = session.game_id
        stale_connections: list[ConnectionProtocol] = []

        try:
            async with lock:
                # Revalidate session state inside the lock to guard against a
                # concurrent reconnect that completed while we waited for the lock.
                current_session = self._session_store.get_session(session_token)
                if current_session is None or current_session.disconnected_at is None:
                    await self._send_error(
                        connection,
                        SessionErrorCode.RECONNECT_NO_SESSION,
                        "No disconnected session found",
                    )
                    return

                # Read bank seconds inside the lock so disconnect processing
                # (which writes remaining_bank_seconds under the same lock)
                # is guaranteed to have completed.
                saved_bank_seconds = current_session.remaining_bank_seconds

                self._evict_stale_connections(game, seat, stale_connections)
                self._game_service.restore_human_player(game_id, seat)

                try:
                    snapshot = self._game_service.build_reconnection_snapshot(game_id, seat)
                except Exception:
                    # Reinstate AI player so the seat isn't orphaned
                    self._game_service.replace_with_ai_player(game_id, session.player_name)
                    raise
                if snapshot is None:
                    self._game_service.replace_with_ai_player(game_id, session.player_name)
                    await self._send_error(
                        connection,
                        SessionErrorCode.RECONNECT_SNAPSHOT_FAILED,
                        "Failed to build game state",
                    )
                    return

                player = self._register_reconnected_player(
                    connection,
                    session,
                    game,
                    seat,
                    saved_bank_seconds,
                )

                # Mark session as reconnected and clear bank state.
                # If the send below fails, the disconnect handler
                # will find the session and mark it disconnected again,
                # allowing the client to retry with the same token.
                self._session_store.mark_reconnected(session_token)
                session.remaining_bank_seconds = None

                payload = snapshot.model_dump(by_alias=True, exclude_none=True)
                payload["type"] = SessionMessageType.GAME_RECONNECTED
                await connection.send_message(payload)

                await self._broadcast_to_game(
                    game=game,
                    message=PlayerReconnectedMessage(
                        player_name=session.player_name,
                    ).model_dump(),
                    exclude_connection_id=connection.connection_id,
                )

                await self._send_turn_state_on_reconnect(game_id, seat, player)
        finally:
            # Close stale sockets outside the game lock, including on failure
            # paths where early returns would otherwise orphan them.
            for stale_conn in stale_connections:
                with contextlib.suppress(RuntimeError, OSError, ConnectionError):
                    await stale_conn.close(code=1000, reason="replaced_by_reconnect")

        structlog.contextvars.bind_contextvars(seat=seat)
        logger.info("player reconnected")

    async def _validate_reconnect(
        self,
        connection: ConnectionProtocol,
        room_id: str,
        session_token: str,
    ) -> tuple[SessionData, Game, asyncio.Lock, int] | None:
        """Validate reconnect preconditions. Returns (session, game, lock, seat) or None on error."""
        result = await self._validate_reconnect_session(connection, room_id, session_token)
        if result is None:
            return None

        session, game, lock, seat = result

        if self.is_in_room(connection.connection_id):
            await self._send_error(
                connection,
                SessionErrorCode.RECONNECT_IN_ROOM,
                "Connection is currently in a room",
            )
            return None

        if self.is_in_active_game(connection.connection_id):
            await self._send_error(
                connection,
                SessionErrorCode.RECONNECT_ALREADY_ACTIVE,
                "Connection already in a game",
            )
            return None

        return session, game, lock, seat

    async def _validate_reconnect_session(
        self,
        connection: ConnectionProtocol,
        room_id: str,
        session_token: str,
    ) -> tuple[SessionData, Game, asyncio.Lock, int] | None:
        """Validate session-level reconnect preconditions."""
        session = self._session_store.get_session(session_token)
        if session is None or session.disconnected_at is None:
            # No session: permanent error. Session exists but not yet
            # disconnected (e.g. client reconnects before server detects the
            # old connection drop): retryable so the client tries again after
            # the server processes the disconnect.
            code = (
                SessionErrorCode.RECONNECT_RETRY_LATER if session is not None else SessionErrorCode.RECONNECT_NO_SESSION
            )
            message = (
                "Session not yet disconnected, retry shortly"
                if session is not None
                else "No disconnected session found"
            )
            await self._send_error(connection, code, message)
            return None

        if session.game_id != room_id:
            await self._send_error(
                connection,
                SessionErrorCode.RECONNECT_GAME_MISMATCH,
                "Session token is not valid for this game",
            )
            return None

        seat = session.seat
        if seat is None:
            await self._send_error(
                connection,
                SessionErrorCode.RECONNECT_NO_SEAT,
                "Session has no seat assignment",
            )
            return None

        game = self._games.get(session.game_id)
        if game is None:
            self._session_store.remove_session(session_token)
            await self._send_error(
                connection,
                SessionErrorCode.RECONNECT_GAME_GONE,
                "Game no longer exists",
            )
            return None

        lock = self._get_game_lock(session.game_id)
        if lock is None:
            await self._send_error(
                connection,
                SessionErrorCode.RECONNECT_RETRY_LATER,
                "Game is starting, retry shortly",
            )
            return None

        return session, game, lock, seat

    def _evict_stale_connections(
        self,
        game: Game,
        seat: int,
        stale_out: list[ConnectionProtocol],
    ) -> None:
        """Remove stale connections at a seat and collect them for closing outside the lock."""
        stale_ids = [cid for cid, p in game.players.items() if p.seat == seat]
        for cid in stale_ids:
            game.players.pop(cid, None)
            self._players.pop(cid, None)
            stale_conn = self._connections.pop(cid, None)
            if stale_conn is not None:
                self._heartbeat.record_disconnect(cid)
                stale_out.append(stale_conn)

    def _register_reconnected_player(
        self,
        connection: ConnectionProtocol,
        session: SessionData,
        game: Game,
        seat: int,
        saved_bank_seconds: float | None,
    ) -> Player:
        """Create and register a reconnected player and set up timer."""
        player = Player(
            connection=connection,
            name=session.player_name,
            session_token=session.session_token,
            user_id=session.user_id,
            game_id=game.game_id,
            seat=seat,
        )
        self._players[connection.connection_id] = player
        game.players[connection.connection_id] = player

        timer_config = TimerConfig.from_settings(game.settings)
        self._timer_manager.add_timer(
            game.game_id,
            seat,
            config=timer_config,
            bank_seconds=saved_bank_seconds,
        )
        return player

    async def _send_turn_state_on_reconnect(
        self,
        game_id: str,
        seat: int,
        player: Player,
    ) -> None:
        """Send draw event for a reconnected player when it is currently their turn.

        Uses direct connection.send_message() instead of _broadcast_events() to avoid
        recording duplicate events in the replay collector.
        """
        game_state = self._game_service.get_game_state(game_id)
        if game_state is None:
            return

        round_state = game_state.round_state
        if round_state.phase != RoundPhase.PLAYING or self._game_service.is_round_advance_pending(game_id):
            return

        prompt = round_state.pending_call_prompt
        if prompt is not None:
            return

        if round_state.current_player_seat == seat:
            events = self._game_service.build_draw_event_for_seat(game_id, seat)
            for event in events:
                message = service_event_payload(event)
                with contextlib.suppress(RuntimeError, OSError, ConnectionError):
                    await player.connection.send_message(message)
            self._timer_manager.start_turn_timer(game_id, seat)

    # --- Room management (delegated to RoomManager) ---

    def create_room(self, room_id: str, num_ai_players: int = 3) -> Room:
        return self._room_manager.create_room(room_id, num_ai_players)

    def get_room(self, room_id: str) -> Room | None:
        return self._room_manager.get_room(room_id)

    def is_in_room(self, connection_id: str) -> bool:
        return self._room_manager.is_in_room(connection_id)

    def is_in_active_game(self, connection_id: str) -> bool:
        player = self._players.get(connection_id)
        return player is not None and player.game_id is not None

    @property
    def room_count(self) -> int:
        return self._room_manager.room_count

    def get_rooms_info(self) -> list[RoomInfo]:
        return self._room_manager.get_rooms_info()

    async def join_room(
        self,
        connection: ConnectionProtocol,
        room_id: str,
        player_name: str,
        user_id: str = "",
        session_token: str = "",
    ) -> None:
        await self._room_manager.join_room(
            connection,
            room_id,
            player_name,
            user_id=user_id,
            session_token=session_token,
        )

    async def leave_room(self, connection: ConnectionProtocol, *, notify_player: bool = True) -> None:
        await self._room_manager.leave_room(connection, notify_player=notify_player)

    async def set_ready(self, connection: ConnectionProtocol, *, ready: bool) -> None:
        await self._room_manager.set_ready(connection, ready=ready)

    async def broadcast_room_chat(self, connection: ConnectionProtocol, text: str) -> None:
        await self._room_manager.broadcast_room_chat(connection, text)

    def start_room_reaper(self) -> None:
        self._room_manager.start_room_reaper()

    async def stop_room_reaper(self) -> None:
        await self._room_manager.stop_room_reaper()

    async def _handle_room_transition(
        self,
        room_id: str,
        room_players: list[RoomPlayer],
        num_ai_players: int,
        settings: GameSettings,
    ) -> None:
        """Create a Game from room players and start the mahjong game."""
        structlog.contextvars.clear_contextvars()
        game = Game(game_id=room_id, num_ai_players=num_ai_players, settings=settings)
        self._games[room_id] = game

        for rp in room_players:
            session = self._session_store.create_session(
                rp.name,
                room_id,
                token=rp.session_token,
                user_id=rp.user_id,
            )
            player = Player(
                connection=rp.connection,
                name=rp.name,
                session_token=session.session_token,
                user_id=rp.user_id,
                game_id=room_id,
            )
            self._players[rp.connection_id] = player
            game.players[rp.connection_id] = player

        message = GameStartingMessage().model_dump()
        for rp in room_players:
            with contextlib.suppress(RuntimeError, OSError):
                await rp.connection.send_message(message)

        await self._start_mahjong_game(game)

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
        await self._record_game_start(game)

        # Third liveness check: if all players disconnected during the
        # _record_game_start await, _cleanup_empty_game already removed
        # the game and cleaned up service/replay state. Bail out to
        # avoid creating stale lock/timer/heartbeat entries.
        if not self._is_game_alive(game):
            return

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

        game_end_events: list[ServiceEvent] = []
        async with self._game_locks[game.game_id]:
            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)
            ai_events = await self._replace_disconnected_players(game, player_names)
            if self._has_game_ended(ai_events):
                game_end_events = ai_events

        # Close connections outside the lock
        if game_end_events:
            await self._close_connections_on_game_end(game, game_end_events)

    async def _replace_disconnected_players(
        self,
        game: Game,
        original_player_names: list[str],
    ) -> list[ServiceEvent]:
        """Replace players who disconnected during start_game or subsequent broadcasts.

        Called under the per-game lock. Players who left before seats/locks
        were set up could not be replaced by leave_game, so handle them here.
        Returns events that may contain a GameEndedEvent (caller handles
        connection closing outside the lock).
        """
        all_events: list[ServiceEvent] = []
        connected_names = set(game.player_names)
        for name in original_player_names:
            if name not in connected_names and not game.is_empty:
                seat = self._game_service.get_player_seat(game.game_id, name)
                if seat is not None:
                    ai_events = await self._replace_with_ai_player(game, name, seat)
                    all_events.extend(ai_events)
                    if self._has_game_ended(ai_events):
                        break
        return all_events

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
        await broadcast_to_players(game.players, message, exclude_connection_id)

    async def _maybe_start_timer(self, game: Game, events: list[ServiceEvent]) -> None:
        """Inspect events and delegate timer actions to TimerManager."""
        game_id = game.game_id

        # game ended -- cancel all timers
        if self._has_game_ended(events):
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
        if not self._has_game_ended(events):
            return
        game.ended = True
        if self._replay_collector:
            await self._replay_collector.save_and_cleanup(game.game_id)
        await self._record_game_finish(game.game_id, "completed")
        for player in list(game.players.values()):
            with contextlib.suppress(RuntimeError, OSError):
                await player.connection.close(code=1000, reason="game_ended")

    def _get_player_at_seat(self, game: Game, seat: int) -> Player | None:
        for player in game.players.values():
            if player.seat == seat:
                return player
        return None

    def _has_game_ended(self, events: list[ServiceEvent]) -> bool:
        return any(isinstance(event.data, GameEndedEvent) for event in events)

    def _has_game_events(self, events: list[ServiceEvent]) -> bool:
        return any(not isinstance(event.data, (ErrorEvent, FuritenEvent)) for event in events)

    def _has_error_events(self, events: list[ServiceEvent]) -> bool:
        return any(isinstance(event.data, ErrorEvent) for event in events)

    async def _handle_timeout(self, game_id: str, timeout_type: TimeoutType, seat: int) -> None:
        lock = self._get_game_lock(game_id)
        if lock is None:
            return

        offender_connection: ConnectionProtocol | None = None
        game_end_events: list[ServiceEvent] = []
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
                offender_connection, ai_events = await self._process_invalid_action(game, e)
                if self._has_game_ended(ai_events):
                    game_end_events = ai_events
            else:
                await self._broadcast_events(game, events)
                await self._maybe_start_timer(game, events)
                if self._has_game_ended(events):
                    game_end_events = events

        # Close connections outside the lock to avoid deadlock risk from
        # connection.close() triggering the WebSocket disconnect handler
        # which calls leave_game (which also acquires the per-game lock).
        if game_end_events:
            await self._close_connections_on_game_end(game, game_end_events)
        await self._close_offender_and_cleanup(offender_connection, game_id, game)
