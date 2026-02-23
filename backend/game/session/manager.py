import asyncio
import contextlib
from dataclasses import dataclass, field
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
from game.session.session_store import SessionStore
from game.session.timer_manager import TimerManager
from shared.dal.models import PlayedGame

if TYPE_CHECKING:
    from game.logic.events import ServiceEvent
    from game.logic.service import GameService
    from game.messaging.protocol import ConnectionProtocol
    from game.server.types import PlayerSpec
    from game.session.replay_collector import ReplayCollector
    from shared.dal.game_repository import GameRepository


@dataclass
class PendingGameInfo:
    """Track state for a game waiting for players to connect via JOIN_GAME."""

    game_id: str
    expected_count: int  # number of human players expected
    connected_count: int = 0
    timeout_task: asyncio.Task[None] | None = None
    player_specs: list[PlayerSpec] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)


logger = structlog.get_logger()


class SessionManager:
    def __init__(
        self,
        game_service: GameService,
        log_dir: str | None = None,
        replay_collector: ReplayCollector | None = None,
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
        self._pending_games: dict[str, PendingGameInfo] = {}  # game_id -> PendingGameInfo
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

    @property
    def pending_game_count(self) -> int:
        return len(self._pending_games)

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
        elif game_id in self._pending_games:
            await self._leave_pending_game(game, connection, player, notify_player=notify_player)
        else:
            # Two cases without a lock:
            # 1. Started game but lock not yet created (disconnect during _start_mahjong_game
            #    setup, before lock/timer infrastructure is ready). _start_mahjong_game
            #    handles AI player replacement for players who left during startup.
            # 2. Pre-start game: no concurrent action/timeout paths.
            if game.started:
                self._session_store.mark_disconnected(player.session_token)
            else:  # pragma: no cover — defensive: unreachable after room removal
                self._session_store.remove_session(player.session_token)
            self._remove_player_from_game(game, connection.connection_id, player)
            await self._notify_player_left(connection, game, player_name, notify_player=notify_player)

        # Don't clean up pending games when they become empty - the timeout
        # task will handle starting the game (with AI substitutes) or cleanup.
        if game_id not in self._pending_games:
            await self._cleanup_empty_game(game_id, game)

    async def _leave_pending_game(
        self,
        game: Game,
        connection: ConnectionProtocol,
        player: Player,
        *,
        notify_player: bool,
    ) -> None:
        """Handle player disconnect from a pending (pre-start) game."""
        pending = self._pending_games.get(game.game_id)
        if pending is not None:
            async with pending.lock:
                # Re-validate after acquiring the lock: if a concurrent JOIN_GAME
                # evicted this connection (replaced by a new one with the same
                # session token), skip all state mutations to avoid corrupting
                # connected_count and the replacement connection's session state.
                if player.game_id is None:
                    return
                pending.connected_count = max(0, pending.connected_count - 1)
                await self._disconnect_pending_player(game, connection, player, notify_player=notify_player)
        else:  # pragma: no cover — defensive: unreachable in asyncio single-threaded model
            if player.game_id is None:
                return
            await self._disconnect_pending_player(game, connection, player, notify_player=notify_player)

    async def _disconnect_pending_player(
        self,
        game: Game,
        connection: ConnectionProtocol,
        player: Player,
        *,
        notify_player: bool,
    ) -> None:
        """Mark session disconnected and remove player from a pending game."""
        self._session_store.mark_disconnected(player.session_token)
        self._remove_player_from_game(game, connection.connection_id, player)
        await self._notify_player_left(connection, game, player.name, notify_player=notify_player)

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
            pending = self._pending_games.pop(game_id, None)
            if pending and pending.timeout_task:
                pending.timeout_task.cancel()
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
        game_id: str,
        session_token: str,
    ) -> None:
        """Handle a player reconnecting to an active game."""
        result = await self._validate_reconnect(connection, game_id, session_token)
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
        game_id: str,
        session_token: str,
    ) -> tuple[SessionData, Game, asyncio.Lock, int] | None:
        """Validate reconnect preconditions. Returns (session, game, lock, seat) or None on error."""
        result = await self._validate_reconnect_session(connection, game_id, session_token)
        if result is None:
            return None

        session, game, lock, seat = result

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
        game_id: str,
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

        if session.game_id != game_id:
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

    # --- Pending game management (direct game creation from lobby) ---

    def create_pending_game(
        self,
        game_id: str,
        player_specs: list[PlayerSpec],
        num_ai_players: int,
    ) -> None:
        """Create a game in pending state, waiting for players to connect via JOIN_GAME."""
        if game_id in self._games or game_id in self._pending_games:
            raise ValueError(f"Game {game_id} already exists")

        game = Game(game_id=game_id, num_ai_players=num_ai_players)
        self._games[game_id] = game

        # Create sessions using game_ticket as the session token, matching what
        # clients will present in JOIN_GAME
        for spec in player_specs:
            self._session_store.create_session(
                spec.name,
                game_id,
                token=spec.game_ticket,
                user_id=spec.user_id,
            )

        expected_count = len(player_specs)
        pending = PendingGameInfo(
            game_id=game_id,
            expected_count=expected_count,
            player_specs=list(player_specs),
        )
        self._pending_games[game_id] = pending

        pending.timeout_task = asyncio.create_task(
            self._pending_game_timeout(game_id, game.settings.pending_game_timeout_seconds),
        )
        logger.info("pending game created", game_id=game_id, expected_count=expected_count)

    async def join_game(
        self,
        connection: ConnectionProtocol,
        game_id: str,
        session_token: str,
    ) -> None:
        """Handle a player connecting to a pending game via JOIN_GAME."""
        # Check for already-started game before looking at pending state
        game = self._games.get(game_id)
        if game is not None and game.started:
            await self._send_error(
                connection,
                SessionErrorCode.JOIN_GAME_ALREADY_STARTED,
                "Game already started, use RECONNECT",
            )
            return

        pending = self._pending_games.get(game_id)
        if pending is None:
            await self._send_error(connection, SessionErrorCode.JOIN_GAME_NOT_FOUND, "Game not found")
            return

        stale_conn: ConnectionProtocol | None = None
        try:
            async with pending.lock:
                # Reject evicted/unregistered connections: after eviction removes
                # a connection from _connections, its message loop may still be
                # running until close() completes. Without this guard the stale
                # socket could re-register itself and evict the replacement.
                if self._connections.get(connection.connection_id) is not connection:
                    return
                error = self._validate_join_game(connection.connection_id, game_id, session_token)
                if error is not None:
                    await self._send_error(connection, *error)
                    return
                stale_conn = await self._register_pending_player(connection, game_id, session_token)
        finally:
            # Close evicted stale socket outside the lock to avoid deadlock
            # (close triggers disconnect handler which calls leave_game).
            if stale_conn is not None:
                with contextlib.suppress(RuntimeError, OSError, ConnectionError):
                    await stale_conn.close(code=1000, reason="replaced_by_new_connection")

    def _validate_join_game(
        self,
        connection_id: str,
        game_id: str,
        session_token: str,
    ) -> tuple[SessionErrorCode, str] | None:
        """Validate a JOIN_GAME request. Returns (error_code, message) or None if valid."""
        existing = self._players.get(connection_id)
        if existing is not None and existing.game_id is not None:
            return SessionErrorCode.ALREADY_IN_GAME, "Connection already in a game"

        session = self._session_store.get_session(session_token)
        if session is None:
            return SessionErrorCode.JOIN_GAME_NO_SESSION, "No session for this ticket"
        if session.game_id != game_id:
            return SessionErrorCode.RECONNECT_GAME_MISMATCH, "Session token is not valid for this game"

        game = self._games.get(game_id)
        if game is None or game_id not in self._pending_games:
            return SessionErrorCode.JOIN_GAME_NOT_FOUND, "Game not found"
        if game.started:
            return SessionErrorCode.JOIN_GAME_ALREADY_STARTED, "Game already started, use RECONNECT"

        return None

    async def _register_pending_player(
        self,
        connection: ConnectionProtocol,
        game_id: str,
        session_token: str,
    ) -> ConnectionProtocol | None:
        """Register a validated player into a pending game. Caller must hold the pending lock.

        Returns the evicted stale connection (if any) for the caller to close
        outside the lock.
        """
        game = self._games.get(game_id)
        pending = self._pending_games.get(game_id)
        session = self._session_store.get_session(session_token)
        if game is None or pending is None or session is None:
            return None

        # If another connection already holds this session, evict it and
        # replace with the new connection (handles stale/zombie sockets).
        evicted = False
        stale_conn: ConnectionProtocol | None = None
        for cid, p in list(game.players.items()):
            if p.session_token == session_token:
                game.players.pop(cid)
                self._players.pop(cid, None)
                stale_conn = self._connections.pop(cid, None)
                if stale_conn is not None:
                    self._heartbeat.record_disconnect(cid)
                p.game_id = None
                p.seat = None
                evicted = True
                logger.info(
                    "evicting stale connection for duplicate JOIN_GAME",
                    game_id=game_id,
                    old_connection_id=cid,
                    new_connection_id=connection.connection_id,
                )
                break

        player = Player(
            connection=connection,
            name=session.player_name,
            session_token=session_token,
            user_id=session.user_id,
            game_id=game_id,
        )
        self._players[connection.connection_id] = player
        game.players[connection.connection_id] = player

        self._session_store.mark_reconnected(session_token)
        # Don't increment connected_count when replacing an existing connection
        if not evicted:
            pending.connected_count += 1

        logger.info(
            "player joined pending game",
            game_id=game_id,
            player_name=session.player_name,
            connected=pending.connected_count,
            expected=pending.expected_count,
        )

        if pending.connected_count >= pending.expected_count:
            if pending.timeout_task is not None:
                pending.timeout_task.cancel()
            await self._complete_pending_game(game_id)

        return stale_conn

    async def _complete_pending_game(self, game_id: str) -> None:
        """Start a pending game. Caller must hold the pending game's lock."""
        pending = self._pending_games.pop(game_id, None)
        if pending is None:
            return  # already started

        if pending.timeout_task is not None:
            pending.timeout_task.cancel()

        game = self._games.get(game_id)
        if game is None:
            return

        # Use all expected human names for game start (including never-connected players)
        all_human_names = [spec.name for spec in pending.player_specs]
        await self._start_mahjong_game(game, player_names_override=all_human_names)

        # After game start, bind seats and mark disconnected for never-connected players
        # so they can reclaim their seat via RECONNECT
        if game.started:
            connected_names = set(game.player_names)
            name_to_token = {spec.name: spec.game_ticket for spec in pending.player_specs}
            for spec in pending.player_specs:
                if spec.name not in connected_names:
                    seat = self._game_service.get_player_seat(game_id, spec.name)
                    if seat is not None:
                        self._session_store.bind_seat(name_to_token[spec.name], seat)
                        self._session_store.mark_disconnected(name_to_token[spec.name])

        logger.info("pending game completed", game_id=game_id)

    async def _pending_game_timeout(self, game_id: str, timeout_seconds: float) -> None:
        """Timeout for pending game: start with AI substitutes for missing players."""
        await asyncio.sleep(timeout_seconds)

        pending = self._pending_games.get(game_id)
        if pending is None:
            return

        async with pending.lock:
            if pending.connected_count == 0:
                logger.warning(
                    "no players connected before timeout, cancelling game",
                    game_id=game_id,
                    expected=pending.expected_count,
                )
                self._pending_games.pop(game_id, None)
                game = self._games.pop(game_id, None)
                if game is not None:
                    self._session_store.cleanup_game(game_id)
                return
            await self._complete_pending_game(game_id)

    def is_in_active_game(self, connection_id: str) -> bool:
        player = self._players.get(connection_id)
        return player is not None and player.game_id is not None

    @property
    def started_game_count(self) -> int:
        """Count of games that have started (excludes pending games)."""
        return sum(1 for g in self._games.values() if g.started)

    def cancel_all_pending_timeouts(self) -> None:
        """Cancel all pending game timeout tasks (for clean shutdown)."""
        for pending in self._pending_games.values():
            if pending.timeout_task is not None:
                pending.timeout_task.cancel()

    def _is_game_alive(self, game: Game, *, allow_empty: bool = False) -> bool:
        """Check if a game is still tracked (and has connected players unless allow_empty)."""
        if self._games.get(game.game_id) is not game:  # pragma: no cover — race condition guard
            return False
        return allow_empty or not game.is_empty

    async def _start_mahjong_game(
        self,
        game: Game,
        player_names_override: list[str] | None = None,
    ) -> None:
        """Start the mahjong game.

        If player_names_override is provided, use those names instead of
        game.player_names. This supports pending games where not all expected
        players may have connected yet.
        """
        allow_empty = player_names_override is not None
        # Guard: if all players disconnected while the pending game was being
        # completed, leave_game may have already cleaned the game out of _games.
        # Starting a game that is no longer tracked would leak locks, heartbeat
        # tasks, and service state. When player_names_override is provided
        # (pending game), skip the "has players" check since the game may
        # legitimately have 0 connected players (all will be AI substitutes).
        if not self._is_game_alive(game, allow_empty=allow_empty):  # pragma: no cover — race condition guard
            return

        game.started = True
        player_names = player_names_override if player_names_override is not None else game.player_names
        events = await self._game_service.start_game(game.game_id, player_names, settings=game.settings)

        # if startup failed (e.g. unsupported settings), rollback and broadcast error
        if any(isinstance(e.data, ErrorEvent) for e in events):
            game.started = False
            await self._broadcast_events(game, events)
            return

        # Second liveness check: if all players disconnected during the
        # start_game await, leave_game may have cleaned the game from _games.
        # Clean up the service state that start_game just created and bail out.
        if not self._is_game_alive(game, allow_empty=allow_empty):  # pragma: no cover — race condition guard
            self._game_service.cleanup_game(game.game_id)
            return

        self._start_replay_collection(game.game_id)
        await self._record_game_start(game)

        # Third liveness check: if all players disconnected during the
        # _record_game_start await, _cleanup_empty_game already removed
        # the game and cleaned up service/replay state. Bail out to
        # avoid creating stale lock/timer/heartbeat entries.
        if not self._is_game_alive(game, allow_empty=allow_empty):  # pragma: no cover — race condition guard
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
            if self._has_game_ended(ai_events):  # pragma: no cover — rare: game ends during AI replacement at start
                game_end_events = ai_events

        # Close connections outside the lock
        if game_end_events:  # pragma: no cover
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
                    if self._has_game_ended(ai_events):  # pragma: no cover — rare: game ends during AI replacement
                        return all_events  # pragma: no cover
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
