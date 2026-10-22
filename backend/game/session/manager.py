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
from game.session.timer_manager import TimerFiring, TimerManager
from shared.dal.models import GameEndReason, PlayedGame, PlayedGameStanding
from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from game.logic.events import ServiceEvent
    from game.logic.service import GameService
    from game.messaging.protocol import ConnectionProtocol
    from game.session.models import PlayerSpec
    from game.session.replay_collector import ReplayCollector
    from shared.dal.game_repository import GameRepository


@dataclass
class PendingGameInfo:
    """
    Track state for a game waiting for players to connect via JOIN_GAME.
    """

    game_id: str
    expected_count: int  # number of human players expected
    connected_count: int = 0
    timeout_task: asyncio.Task[None] | None = None
    player_specs: list[PlayerSpec] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)


@dataclass(frozen=True)
class _FailedGame:
    """
    What fail_game detached from a failed game for its finalizer: the game, its players, heartbeat loop and replay.
    """

    game: Game
    players: list[Player]
    heartbeat: asyncio.Task[None] | None
    replay_lines: list[str] | None


logger = structlog.get_logger()


_AUTH_TIMEOUT_SECONDS = 10


class SessionManager:
    def __init__(
        self,
        game_service: GameService,
        replay_collector: ReplayCollector | None = None,
        game_repository: GameRepository | None = None,
    ) -> None:
        self._game_service = game_service
        self._game_repository = game_repository
        self._replay_collector = replay_collector

        self._connections: dict[str, ConnectionProtocol] = {}
        self._players: dict[str, Player] = {}  # connection_id -> Player
        self._games: dict[str, Game] = {}  # game_id -> Game

        self._session_store = SessionStore()
        self._timer_manager = TimerManager(on_timeout=self._handle_timeout)
        self._game_locks: dict[str, asyncio.Lock] = {}  # game_id -> Lock
        self._pending_games: dict[str, PendingGameInfo] = {}  # game_id -> PendingGameInfo

        self._heartbeat = HeartbeatMonitor()
        self._auth_timeouts: dict[str, asyncio.Task[None]] = {}  # connection_id -> timeout task
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """
        Start a background task the manager owns until it finishes; shutdown waits for it.
        """
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def _get_game_lock(self, game_id: str) -> asyncio.Lock | None:
        """
        Get the per-game lock, or None if the game has no lock (not yet started or already cleaned up).
        """
        return self._game_locks.get(game_id)

    def register_connection(self, connection: ConnectionProtocol) -> None:
        self._connections[connection.connection_id] = connection
        self._heartbeat.record_connect(connection.connection_id)
        # RuntimeError is suppressed for synchronous test contexts without
        # a running event loop. In production, register_connection is always
        # called from within the ASGI event loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return

        self._auth_timeouts[connection.connection_id] = self._spawn(self._auth_timeout(connection))

    def unregister_connection(self, connection: ConnectionProtocol) -> None:
        self._connections.pop(connection.connection_id, None)
        self._players.pop(connection.connection_id, None)
        self._heartbeat.record_disconnect(connection.connection_id)
        self._cancel_auth_timeout(connection.connection_id)

    def get_game(self, game_id: str) -> Game | None:
        return self._games.get(game_id)

    def get_connection_game(self, connection: ConnectionProtocol) -> Game | None:
        """
        Return the game the connection's player is in, or None.
        """
        player = self._players.get(connection.connection_id)
        return self._game_of(player) if player is not None else None

    def _game_of(self, player: Player) -> Game | None:
        """
        Return the registered game the player is seated in; None once it is gone, even if its id now names another.
        """
        game = self._games.get(player.game_id) if player.game_id is not None else None
        if game is None or game.players.get(player.connection_id) is not player:
            return None

        return game

    @property
    def game_count(self) -> int:
        return len(self._games)

    @property
    def pending_game_count(self) -> int:
        return len(self._pending_games)

    def _start_replay_collection(self, game_id: str) -> None:
        """
        Start replay collection with the game seed (known after game_service.start_game).
        """
        if self._replay_collector:
            seed = self._game_service.get_game_seed(game_id)
            if seed is not None:
                game_state = self._game_service.get_game_state(game_id)
                rng_version = game_state.rng_version if game_state is not None else ""
                self._replay_collector.start_game(game_id=game_id, seed=seed, rng_version=rng_version)

    async def _record_game_start(
        self,
        game: Game,
        user_ids_by_name: dict[str, str] | None = None,
    ) -> None:
        """
        Best-effort persist game start to the game repository.
        """
        if self._game_repository is None:
            return

        game_state = self._game_service.get_game_state(game.game_id)
        if game_state is None:
            return

        # Map names to user_ids: use override for pending games (includes never-connected
        # humans), fall back to connected players only (normal start flow).
        name_to_uid = user_ids_by_name or {p.name: p.user_id for p in game.players.values() if p.user_id}

        standings = [
            PlayedGameStanding(
                name=p.name,
                seat=p.seat,
                user_id=name_to_uid.get(p.name, ""),
            )
            for p in game_state.round_state.players
        ]

        played_game = PlayedGame(
            game_id=game.game_id,
            started_at=datetime.now(UTC),
            game_type=game_state.settings.game_type,
            standings=standings,
        )
        try:
            await self._game_repository.create_game(played_game)
        except Exception:
            logger.exception("failed to persist game start")

    async def _record_game_finish(
        self,
        game_id: str,
        end_reason: GameEndReason,
        game_ended_event: GameEndedEvent | None = None,
    ) -> None:
        """
        Best-effort persist game end to the game repository.
        """
        if self._game_repository is None:
            return

        standings = None
        num_rounds_played = None
        if game_ended_event is not None:
            num_rounds_played = game_ended_event.num_rounds if game_ended_event.num_rounds > 0 else None
            try:
                # Read existing game record to preserve user_ids and names from game start
                # (game state is unavailable here -- auto_cleanup runs before events are returned)
                existing = await self._game_repository.get_game(game_id)
                uid_by_seat = {s.seat: s.user_id for s in existing.standings} if existing else {}
                names_by_seat = {s.seat: s.name for s in existing.standings} if existing else {}
            except Exception:
                logger.exception("failed to read existing game for standings enrichment", game_id=game_id)
                uid_by_seat = {}
                names_by_seat = {}

            # Preserve the game logic's placement order (handles tiebreaking by seat
            # proximity to dealer) -- do NOT re-sort by final_score.
            standings = [
                PlayedGameStanding(
                    name=names_by_seat.get(s.seat, ""),
                    seat=s.seat,
                    user_id=uid_by_seat.get(s.seat, ""),
                    score=s.score,
                    final_score=s.final_score,
                )
                for s in game_ended_event.standings
            ]

        try:
            await self._game_repository.finish_game(
                game_id=game_id,
                ended_at=datetime.now(UTC),
                end_reason=end_reason,
                num_rounds_played=num_rounds_played,
                standings=standings,
            )
        except Exception:
            logger.exception("failed to persist game end")

    async def _send_error(self, connection: ConnectionProtocol, *, code: SessionErrorCode, message: str) -> None:
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

        game = self._game_of(player)
        if game is None:
            if player.game_id not in self._games:
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
            async with lock:
                self._session_store.mark_disconnected(player.session_token)
                self._remove_player_from_game(game, connection_id=connection.connection_id, player=player)
                await self._notify_player_left(connection, game, player_name, notify_player=notify_player)
                # replace disconnected player with AI player (only if other players remain)
                if not game.is_empty and player_seat is not None:
                    await self._replace_with_ai_player(
                        game, player_name=player_name, seat=player_seat, session_token=player.session_token
                    )
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
            else:
                self._session_store.remove_session(player.session_token)

            self._remove_player_from_game(game, connection_id=connection.connection_id, player=player)
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
        """
        Handle player disconnect from a pending (pre-start) game.
        """
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
        """
        Mark session disconnected and remove player from a pending game.
        """
        self._session_store.mark_disconnected(player.session_token)
        self._remove_player_from_game(game, connection_id=connection.connection_id, player=player)
        await self._notify_player_left(connection, game, player.name, notify_player=notify_player)

    @staticmethod
    def _remove_player_from_game(game: Game, connection_id: str, player: Player) -> None:
        """
        Remove a player from a game and clear their game association.
        """
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
        """
        Send leave notification to the player and broadcast departure to the game.
        """
        if notify_player:
            with contextlib.suppress(RuntimeError, OSError):
                await connection.send_message(GameLeftMessage().model_dump())

        await self._broadcast_to_game(
            game=game,
            message=PlayerLeftMessage(player_name=player_name).model_dump(),
        )

    async def _cleanup_empty_game(self, game_id: str, game: Game) -> None:
        """
        Clean up an empty game: remove from registry, stop timers/heartbeat, cleanup service state.

        Everything keyed by the game id is released before the first await, so a new game registered under the same id
        afterwards is left alone.
        """
        if not game.is_empty or self._games.get(game_id) is not game:
            return

        logger.info("game is empty, cleaning up")
        self._games.pop(game_id)
        abandoned = game.started and not game.ended
        self._session_store.cleanup_game(game_id)
        self._timer_manager.cleanup_game(game_id)
        self._game_locks.pop(game_id, None)
        self._game_service.cleanup_game(game_id)
        if self._replay_collector:
            self._replay_collector.cleanup_game(game_id)

        await self._heartbeat.stop_for_game(game_id)
        if abandoned:
            await self._record_game_finish(game_id=game_id, end_reason=GameEndReason.ABANDONED)

    async def _replace_with_ai_player(
        self,
        game: Game,
        player_name: str,
        seat: int,
        session_token: str | None = None,
    ) -> None:
        """
        Replace a disconnected player with an AI player and process any pending AI player actions.

        Must be called under the per-game lock (leave_game acquires it). Must be called BEFORE the is_empty cleanup
        check, and only when other players remain in the game. AI events that end the game finish it through
        `_broadcast_events`.
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

    async def _handle_invalid_action(
        self,
        game: Game,
        connection: ConnectionProtocol,
        player: Player,
        error: InvalidGameActionError,
    ) -> None:
        """
        Handle a provably invalid game action: log, disconnect, replace with AI player.

        Must be called under the per-game lock. Connection close and empty-game cleanup happen OUTSIDE the lock (by the
        caller).
        """
        player_name = player.name
        player_seat = player.seat

        logger.warning("invalid game action", action=error.action, reason=error.reason)

        self._session_store.mark_disconnected(player.session_token)
        self._remove_player_from_game(game, connection_id=connection.connection_id, player=player)

        await self._broadcast_to_game(
            game=game,
            message=PlayerLeftMessage(player_name=player_name).model_dump(),
        )

        if not game.is_empty and player_seat is not None:
            await self._replace_with_ai_player(
                game, player_name=player_name, seat=player_seat, session_token=player.session_token
            )

    async def _process_successful_action(
        self,
        game: Game,
        game_id: str,
        player: Player,
        events: list[ServiceEvent],
    ) -> None:
        """
        Handle timer management and broadcasting after a successful game action.
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

    async def _process_invalid_action(
        self,
        game: Game,
        error: InvalidGameActionError,
    ) -> ConnectionProtocol | None:
        """
        Handle InvalidGameActionError under the lock.

        Returns the offender connection, which the caller closes outside the lock.
        """
        # resolve offender by seat from exception (critical for resolution-triggered errors)
        offender_player = self._get_player_at_seat(game, error.seat)
        if offender_player is None:
            # offending seat has no connected player (AI player seat) — log and skip disconnect
            logger.warning("invalid action at AI player seat, skipping disconnect", error_seat=error.seat)
            return None

        offender_connection = offender_player.connection
        try:
            await self._handle_invalid_action(game, offender_connection, player=offender_player, error=error)
        except (RuntimeError, OSError, ConnectionError, ValueError, InvalidGameActionError):  # fmt: skip
            logger.exception("error during invalid action handling, player already removed, continuing with disconnect")

        return offender_connection

    async def _close_offender_and_cleanup(
        self,
        offender_connection: ConnectionProtocol | None,
        game_id: str,
        game: Game,
    ) -> None:
        """
        Close the offender's connection and clean up the game if empty.

        Called OUTSIDE the per-game lock to avoid deadlock risk from connection.close() triggering WebSocket disconnect
        handler.
        """
        if offender_connection is None:
            return

        with contextlib.suppress(RuntimeError, OSError):
            await offender_connection.close(code=1008, reason="invalid_game_action")

        await self._cleanup_empty_game(game_id, game)

    async def handle_game_action(
        self,
        connection: ConnectionProtocol,
        *,
        action: GameAction,
        data: dict[str, Any],
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            await self._send_error(connection, code=SessionErrorCode.NOT_IN_GAME, message="You must join a game first")
            return

        game = self._game_of(player)
        if game is None:
            return

        game_id = player.game_id
        structlog.contextvars.bind_contextvars(seat=player.seat)
        lock = self._get_game_lock(game_id)
        if lock is None:
            await self._send_error(
                connection, code=SessionErrorCode.GAME_NOT_STARTED, message="Game has not started yet"
            )
            return

        offender_connection: ConnectionProtocol | None = None
        async with lock:
            if game.ended:
                return

            try:
                events = await self._game_service.handle_action(
                    game_id=game_id,
                    player_name=player.name,
                    action=action,
                    data=data,
                )
            except InvalidGameActionError as e:
                offender_connection = await self._process_invalid_action(game, e)
            else:
                await self._process_successful_action(game, game_id=game_id, player=player, events=events)

        await self._close_offender_and_cleanup(offender_connection, game_id=game_id, game=game)

    async def broadcast_chat(
        self,
        connection: ConnectionProtocol,
        text: str,
    ) -> None:
        player = self._players.get(connection.connection_id)
        if player is None or player.game_id is None:
            await self._send_error(connection, code=SessionErrorCode.NOT_IN_GAME, message="You must join a game first")
            return

        game = self._game_of(player)
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
        """
        Respond to client ping with pong and update activity timestamp.
        """
        self._heartbeat.record_ping(connection.connection_id)
        await connection.send_message(PongMessage().model_dump())

    # --- Reconnection ---

    async def reconnect(
        self,
        connection: ConnectionProtocol,
        *,
        game_id: str,
        session_token: str,
    ) -> None:
        """
        Handle a player reconnecting to an active game.
        """
        result = await self._validate_reconnect(connection, game_id=game_id, session_token=session_token)
        if result is None:
            return

        session, game, lock, seat = result
        game_id = session.game_id

        stale_connections: list[ConnectionProtocol] = []
        try:
            async with lock:
                # Reject connections closed by auth timeout while we waited
                # for the lock. The timeout removes the connection from
                # _connections before closing, so this identity check fails.
                if self._connections.get(connection.connection_id) is not connection:
                    return

                if game.ended:
                    await self._send_error(
                        connection,
                        code=SessionErrorCode.RECONNECT_GAME_GONE,
                        message="Game has ended",
                    )
                    return

                # Revalidate session state inside the lock to guard against a
                # concurrent reconnect that completed while we waited for the lock.
                current_session = self._session_store.get_session(session_token)
                if current_session is None or current_session.disconnected_at is None:
                    await self._send_error(
                        connection,
                        code=SessionErrorCode.RECONNECT_NO_SESSION,
                        message="No disconnected session found",
                    )
                    return

                # Read bank seconds inside the lock so disconnect processing
                # (which writes remaining_bank_seconds under the same lock)
                # is guaranteed to have completed.
                saved_bank_seconds = current_session.remaining_bank_seconds

                self._evict_stale_connections(game, seat=seat, stale_out=stale_connections)
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
                        code=SessionErrorCode.RECONNECT_SNAPSHOT_FAILED,
                        message="Failed to build game state",
                    )
                    return

                player = self._register_reconnected_player(
                    connection,
                    session,
                    game=game,
                    seat=seat,
                    saved_bank_seconds=saved_bank_seconds,
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

                await self._send_turn_state_on_reconnect(game_id=game_id, seat=seat, player=player)
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
        """
        Validate reconnect preconditions.

        Returns (session, game, lock, seat) or None on error.
        """
        result = await self._validate_reconnect_session(connection, game_id=game_id, session_token=session_token)
        if result is None:
            return None

        session, game, lock, seat = result

        if self.is_in_active_game(connection.connection_id):
            await self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_ALREADY_ACTIVE,
                message="Connection already in a game",
            )
            return None

        return session, game, lock, seat

    async def _validate_reconnect_session(
        self,
        connection: ConnectionProtocol,
        game_id: str,
        session_token: str,
    ) -> tuple[SessionData, Game, asyncio.Lock, int] | None:
        """
        Validate session-level reconnect preconditions.
        """
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
            await self._send_error(connection, code=code, message=message)
            return None

        if session.game_id != game_id:
            await self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_GAME_MISMATCH,
                message="Session token is not valid for this game",
            )
            return None

        seat = session.seat
        if seat is None:
            await self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_NO_SEAT,
                message="Session has no seat assignment",
            )
            return None

        game = self._games.get(session.game_id)
        if game is None:
            self._session_store.remove_session(session_token)
            await self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_GAME_GONE,
                message="Game no longer exists",
            )
            return None

        lock = self._get_game_lock(session.game_id)
        if lock is None:
            await self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_RETRY_LATER,
                message="Game is starting, retry shortly",
            )
            return None

        return session, game, lock, seat

    def _evict_stale_connections(
        self,
        game: Game,
        seat: int,
        stale_out: list[ConnectionProtocol],
    ) -> None:
        """
        Remove stale connections at a seat and collect them for closing outside the lock.
        """
        stale_ids = [cid for cid, p in game.players.items() if p.seat == seat]
        for cid in stale_ids:
            game.players.pop(cid, None)
            self._players.pop(cid, None)
            stale_conn = self._connections.pop(cid, None)
            if stale_conn is not None:
                self._heartbeat.record_disconnect(cid)
                self._cancel_auth_timeout(cid)
                stale_out.append(stale_conn)

    def _register_reconnected_player(
        self,
        connection: ConnectionProtocol,
        session: SessionData,
        game: Game,
        seat: int,
        saved_bank_seconds: float | None,
    ) -> Player:
        """
        Create and register a reconnected player and set up timer.
        """
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
        self._cancel_auth_timeout(connection.connection_id)

        timer_config = TimerConfig.from_settings(game.settings)
        self._timer_manager.add_timer(
            game_id=game.game_id,
            seat=seat,
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
        """
        Send draw event for a reconnected player when it is currently their turn.

        Uses direct connection.send_message() instead of _broadcast_events() to avoid recording duplicate events in the
        replay collector.
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
        *,
        game_id: str,
        player_specs: list[PlayerSpec],
        num_ai_players: int,
    ) -> None:
        """
        Create a game in pending state, waiting for players to connect via JOIN_GAME.
        """
        if game_id in self._games or game_id in self._pending_games:
            raise ValueError(f"Game {game_id} already exists")

        game = Game(game_id=game_id, num_ai_players=num_ai_players)
        self._games[game_id] = game

        # Create sessions using game_ticket as the session token, matching what
        # clients will present in JOIN_GAME
        for spec in player_specs:
            self._session_store.create_session(
                player_name=spec.name,
                game_id=game_id,
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

        pending.timeout_task = self._spawn(
            self._pending_game_timeout(game, game.settings.pending_game_timeout_seconds),
        )
        logger.info("pending game created", game_id=game_id, expected_count=expected_count)

    async def join_game(
        self,
        connection: ConnectionProtocol,
        *,
        game_id: str,
        session_token: str,
    ) -> None:
        """
        Handle a player connecting to a pending game via JOIN_GAME.
        """
        # Check for already-started game before looking at pending state
        game = self._games.get(game_id)
        if game is not None and game.started:
            await self._send_error(
                connection,
                code=SessionErrorCode.JOIN_GAME_ALREADY_STARTED,
                message="Game already started, use RECONNECT",
            )
            return

        pending = self._pending_games.get(game_id)
        if pending is None:
            await self._send_error(connection, code=SessionErrorCode.JOIN_GAME_NOT_FOUND, message="Game not found")
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

                error = self._validate_join_game(
                    connection_id=connection.connection_id, game_id=game_id, session_token=session_token
                )
                if error is not None:
                    code, message = error
                    await self._send_error(connection, code=code, message=message)
                    return

                stale_conn = await self._register_pending_player(
                    connection, game_id=game_id, session_token=session_token
                )
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
        """
        Validate a JOIN_GAME request.

        Returns (error_code, message) or None if valid.
        """
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
        """
        Register a validated player into a pending game.

        Caller must hold the pending lock. Returns the evicted stale connection (if any) for the caller to close outside
        the lock.
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
                    self._cancel_auth_timeout(cid)

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
        self._cancel_auth_timeout(connection.connection_id)

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
        """
        Start a pending game.

        Caller must hold the pending game's lock.
        """
        pending = self._pending_games.pop(game_id, None)
        if pending is None:
            return  # already started

        game = self._games.get(game_id)
        if game is None:
            return

        await self._start_mahjong_game(game, pending.player_specs)
        logger.info("pending game completed", game_id=game_id)

    async def _pending_game_timeout(self, game: Game, timeout_seconds: float) -> None:
        """
        Timeout for pending game: start with AI substitutes for missing players.

        After its sleep the task detaches itself from the pending game, so the completion it runs (or a final join
        racing it) never cancels it. Any unexpected error ends the game through fail_game.
        """
        await asyncio.sleep(timeout_seconds)

        game_id = game.game_id
        pending = self._pending_games.get(game_id)
        if pending is None or self._games.get(game_id) is not game:
            return

        pending.timeout_task = None
        try:
            async with pending.lock:
                await self._resolve_pending_timeout(game, pending)
        except Exception as exc:  # noqa: BLE001
            self.fail_game(game, reason="pending game timeout failed", exc=exc)

    async def _resolve_pending_timeout(self, game: Game, pending: PendingGameInfo) -> None:
        """
        Start the pending game with AI substitutes, or cancel it when nobody joined.

        Caller must hold the pending game's lock.
        """
        game_id = game.game_id
        if self._pending_games.get(game_id) is not pending:
            return

        if pending.connected_count == 0:
            logger.warning(
                "no players connected before timeout, cancelling game",
                game_id=game_id,
                expected=pending.expected_count,
            )
            self._pending_games.pop(game_id, None)
            self._games.pop(game_id, None)
            self._session_store.cleanup_game(game_id)
            return

        await self._complete_pending_game(game_id)

    def get_playing_game_id(self, user_id: str) -> str | None:
        """
        Return the id of the game the user is playing, or None.

        A user plays a game from its creation (pending included) until it ends: any session of theirs in a registered
        game that has not ended counts, connected or not. A disconnected player keeps counting on purpose, so the lobby
        keeps them out of rooms and matchmaking until that game ends.
        """
        for session in self._session_store.get_user_sessions(user_id):
            game = self._games.get(session.game_id)
            if game is not None and not game.ended:
                return game.game_id

        return None

    def is_in_active_game(self, connection_id: str) -> bool:
        player = self._players.get(connection_id)
        return player is not None and player.game_id is not None

    @property
    def started_game_count(self) -> int:
        """
        Count of games that have started (excludes pending games).
        """
        return sum(1 for g in self._games.values() if g.started)

    async def shutdown(self) -> None:
        """
        Stop every background task before the server's resources close.

        Sleeping pending, auth and turn timers and the heartbeat loops are cancelled; a task already past its sleep (a
        pending game completing, an auth close, a timer callback or a failed game's finalizer) is awaited, so its replay
        save, database write and socket closes finish first. Games still running are not recorded as ended.
        """
        sleeping = [pending.timeout_task for pending in self._pending_games.values() if pending.timeout_task]
        sleeping.extend(self._auth_timeouts.values())
        self._auth_timeouts.clear()
        await cancel_and_wait(sleeping, finalizing=list(self._background_tasks))
        await self._timer_manager.shutdown()
        await self._heartbeat.shutdown()
        await cancel_and_wait([], finalizing=list(self._background_tasks))

    def _cancel_auth_timeout(self, connection_id: str) -> None:
        """
        Cancel the auth timeout for a specific connection.
        """
        task = self._auth_timeouts.pop(connection_id, None)
        if task is not None:
            task.cancel()

    async def _auth_timeout(self, connection: ConnectionProtocol) -> None:
        """
        Close an unauthenticated connection after a timeout.

        The task detaches itself from `_auth_timeouts` after its sleep, so cancel paths leave the close alone. An
        unexpected error is logged and the connection closed with 1011: there is no game to fail yet.
        """
        await asyncio.sleep(_AUTH_TIMEOUT_SECONDS)

        self._auth_timeouts.pop(connection.connection_id, None)
        try:
            await self._close_unauthenticated(connection)
        except Exception:
            logger.exception("auth timeout failed", connection_id=connection.connection_id)
            with contextlib.suppress(RuntimeError, OSError):
                await connection.close(code=1011, reason="internal_error")

    async def _close_unauthenticated(self, connection: ConnectionProtocol) -> None:
        cid = connection.connection_id

        # Connection already authenticated or removed
        if cid in self._players or cid not in self._connections:
            return

        # Remove from _connections before closing to prevent a concurrent
        # join_game/reconnect from registering this closing connection.
        # The identity check in join_game (and reconnect) will fail because
        # the connection is no longer in _connections.
        self._connections.pop(cid, None)
        self._heartbeat.record_disconnect(cid)

        logger.info("auth timeout, closing unauthenticated connection", connection_id=cid)
        with contextlib.suppress(RuntimeError, OSError, ConnectionError):
            await connection.close(code=4001, reason="auth_timeout")

    def _is_game_alive(self, game: Game) -> bool:
        """
        Check if this game object is still the one tracked under its id.
        """
        return self._games.get(game.game_id) is game

    async def _start_mahjong_game(self, game: Game, player_specs: list[PlayerSpec]) -> None:
        """
        Start the mahjong game for every expected human, connected or not.

        The game may legitimately have no connected player yet (all seats then go to AI substitutes), so the liveness
        checks allow an empty game. Every expected human's seat is bound while the engine still knows them as human; an
        absent one is marked disconnected, so it can RECONNECT, and then replaced by an AI player.
        """
        if not self._is_game_alive(game):  # pragma: no cover — race condition guard
            return

        game.started = True
        player_names = [spec.name for spec in player_specs]
        events = await self._game_service.start_game(game.game_id, player_names, settings=game.settings)
        # if startup failed (e.g. unsupported settings), rollback and broadcast error
        if any(isinstance(e.data, ErrorEvent) for e in events):
            game.started = False
            await self._broadcast_events(game, events)
            return

        # Second liveness check: if all players disconnected during the
        # start_game await, leave_game may have cleaned the game from _games.
        # Clean up the service state that start_game just created and bail out.
        if not self._is_game_alive(game):  # pragma: no cover — race condition guard
            self._game_service.cleanup_game(game.game_id)
            return

        self._start_replay_collection(game.game_id)
        await self._record_game_start(game, user_ids_by_name={spec.name: spec.user_id for spec in player_specs})

        # Third liveness check: if all players disconnected during the
        # _record_game_start await, _cleanup_empty_game already removed
        # the game and cleaned up service/replay state. Bail out to
        # avoid creating stale lock/timer/heartbeat entries.
        if not self._is_game_alive(game):  # pragma: no cover — race condition guard
            return

        absent_seats = self._bind_seats(game, player_specs)

        seats = [p.seat for p in game.players.values() if p.seat is not None]
        timer_config = TimerConfig.from_settings(game.settings)
        self._timer_manager.create_timers(game_id=game.game_id, seats=seats, config=timer_config)
        self._game_locks[game.game_id] = asyncio.Lock()
        self._heartbeat.start_for_game(
            game.game_id,
            self.get_game,
            on_error=lambda exc: self.fail_game(game, reason="heartbeat loop failed", exc=exc),
        )

        async with self._game_locks[game.game_id]:
            await self._broadcast_events(game, events)
            await self._maybe_start_timer(game, events)
            await self._replace_absent_players(game, absent_seats)

    def _bind_seats(self, game: Game, player_specs: list[PlayerSpec]) -> dict[str, int]:
        """
        Bind every expected human's session to its seat; return the seats of those not connected, by name.

        Must run before any AI replacement: the engine finds a seat by name only while its player is human.
        """
        connected = {player.session_token: player for player in game.players.values()}
        absent_seats: dict[str, int] = {}
        for spec in player_specs:
            seat = self._game_service.get_player_seat(game.game_id, spec.name)
            player = connected.get(spec.game_ticket)
            if seat is not None and player is not None:
                player.seat = seat
                self._session_store.bind_seat(spec.game_ticket, seat)
            elif seat is not None:
                self._session_store.bind_seat(spec.game_ticket, seat)
                self._session_store.mark_disconnected(spec.game_ticket)
                absent_seats[spec.name] = seat

        return absent_seats

    async def _replace_absent_players(self, game: Game, absent_seats: dict[str, int]) -> None:
        """
        Seat AI players for the humans absent at start (never connected, or left before the lock existed).

        Called under the per-game lock. A replacement after one that ended the game is a no-op on the finished engine
        state.
        """
        for name, seat in absent_seats.items():
            if not game.is_empty:
                await self._replace_with_ai_player(game, player_name=name, seat=seat)

    async def _broadcast_events(
        self,
        game: Game,
        events: list[ServiceEvent],
    ) -> None:
        """
        Broadcast events with target-based filtering using typed targets.

        A batch that ends the game claims the completion before its first send, so a fail_game during the broadcast
        finds the game already ended, and the claim's owner is bound to finish the game: after the broadcast it runs the
        completion finalization on the detached replay and the players, and if the broadcast raises it escalates its own
        claim to a failure instead.
        """
        claimed = self._claim_completion(game, events)
        try:
            await self._send_events(game, events)
        except Exception as exc:
            if not claimed:
                raise

            self._escalate_completion(game, exc=exc, replay_lines=self._detach_replay(game))
            return

        if claimed:
            players = list(game.players.values())
            await self._finish_completed_game(game, events, players, self._detach_replay(game))

    def _detach_replay(self, game: Game) -> list[str] | None:
        return self._replay_collector.detach_game(game.game_id) if self._replay_collector else None

    async def _send_events(self, game: Game, events: list[ServiceEvent]) -> None:
        if self._replay_collector:
            self._replay_collector.collect_events(game.game_id, events)

        seat_to_player = {p.seat: p for p in game.players.values() if p.seat is not None}

        for event in events:
            message = service_event_payload(event)
            if isinstance(event.data, CallPromptEvent):
                message = shape_call_prompt_payload(message)

            if isinstance(event.target, BroadcastTarget):
                await self._broadcast_to_game(game, message=message)
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
        await broadcast_to_players(players=game.players, message=message, exclude_connection_id=exclude_connection_id)

    async def _maybe_start_timer(self, game: Game, events: list[ServiceEvent]) -> None:
        """
        Inspect events and delegate timer actions to TimerManager.
        """
        game_id = game.game_id

        # game ended -- cancel all timers
        if self._has_game_ended(events):
            self._timer_manager.cancel_all(game_id)
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
        """
        Start a turn timer if events contain a DrawEvent or a pon/chi MeldEvent.
        """
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
        """
        Start meld timers for connected callers from per-seat CallPromptEvent wrappers.
        """
        for event in events:
            if isinstance(event.data, CallPromptEvent) and isinstance(event.target, SeatTarget):
                seat = event.target.seat
                if self._get_player_at_seat(game, seat) is not None:
                    self._timer_manager.start_meld_timer(game.game_id, seat)

    def fail_game(self, game: Game, *, reason: str, exc: BaseException | None = None) -> bool:
        """
        End a game on a server fault.

        Callable from any context: under the game lock or a pending lock, from a background task, before a connection
        is registered, before the game started. Synchronously, before anything can suspend, it claims the game's end
        (`end_reason=ERROR`) and drops the game from the registry with its pending entry, sleeping timers, lock, engine
        state and sessions, so a new action, timeout, join or reconnect finds no game and no other path can finalize
        it. It also detaches the heartbeat loop and the replay lines, so its finalizer works on those objects and a new
        game started under the same id meanwhile keeps its own. An action, timeout or reconnect already waiting on the
        game lock checks `ended` and stops; a leave already waiting still removes its player and may broadcast
        `player_left` before the internal error. The effects run in a background finalizer the manager owns, with no
        lock held: record the error end, save whatever replay history exists, send every connected player an
        `internal_error` session error, close with 1011. The current task is never cancelled or awaited.

        Returns True when this call ended the game; False when a completion or an earlier failure already claimed its
        end, or it is not this registered game (a reused game id), which makes it idempotent. Either way the caller
        skips its normal broadcast and timers. A completion is never taken over from outside: only the path that claimed
        it escalates its own claim to this failure (`_escalate_completion`) when finishing it raises.
        """
        game_id = game.game_id
        logger.error("game failed", game_id=game_id, reason=reason, exc_info=exc)
        if game.ended or self._games.get(game_id) is not game:
            return False

        game.end_reason = GameEndReason.ERROR
        self._spawn(self._finish_failed_game(self._detach_failed_game(game, replay_lines=self._detach_replay(game))))
        return True

    def _escalate_completion(self, game: Game, *, exc: Exception, replay_lines: list[str] | None) -> None:
        """
        Turn the caller's own completion claim into a failure after an unexpected error while finishing the game.

        Only the path that claimed the completion calls this; a concurrent fail_game still finds the game ended. The
        failure finalizer then records the error end, saves the replay lines the completion had not saved, sends
        `internal_error` and closes with 1011.
        """
        logger.error("game failed while finishing its completion", game_id=game.game_id, exc_info=exc)
        game.end_reason = GameEndReason.ERROR
        self._spawn(self._finish_failed_game(self._detach_failed_game(game, replay_lines=replay_lines)))

    def _detach_failed_game(self, game: Game, *, replay_lines: list[str] | None) -> _FailedGame:
        """
        Release a failed game from the registry and detach what its finalizer needs, synchronously.

        A game no longer registered (its players already left, or its id now names another game) keeps nothing to
        release, and the id-keyed stores are left to whoever owns them now.
        """
        game_id = game.game_id
        heartbeat: asyncio.Task[None] | None = None
        if self._games.get(game_id) is game:
            self._games.pop(game_id)
            pending = self._pending_games.pop(game_id, None)
            if pending is not None and pending.timeout_task is not None:
                pending.timeout_task.cancel()

            self._timer_manager.cleanup_game(game_id)
            self._game_locks.pop(game_id, None)
            self._game_service.cleanup_game(game_id)
            self._session_store.cleanup_game(game_id)
            heartbeat = self._heartbeat.detach_for_game(game_id)

        return _FailedGame(
            game=game,
            players=list(game.players.values()),
            heartbeat=heartbeat,
            replay_lines=replay_lines,
        )

    async def _finish_failed_game(self, failed: _FailedGame) -> None:
        """
        Run the effects of fail_game: finish record, replay, internal error to every player, close with 1011.

        Works only on what fail_game detached, never by game id lookups that a new game under the same id would answer.
        Each step is its own error boundary: an unexpected failure is logged at error level and the steps after it,
        down to the last player's close, still run.
        """
        game_id = failed.game.game_id
        if failed.heartbeat is not None:
            await cancel_and_wait([failed.heartbeat])

        if failed.game.started:
            await self._record_game_finish(game_id=game_id, end_reason=GameEndReason.ERROR)

        try:
            if self._replay_collector:
                await self._replay_collector.save(game_id, failed.replay_lines)
        except Exception:
            logger.exception("failed to save the replay of a failed game", game_id=game_id)

        for player in failed.players:
            await self._close_with_internal_error(player.connection)

    async def _close_with_internal_error(self, connection: ConnectionProtocol) -> None:
        message = ErrorMessage(code=SessionErrorCode.INTERNAL_ERROR, message="The game ended on a server error")
        try:
            try:
                await connection.send_message(message.model_dump())
            finally:
                await connection.close(code=1011, reason="internal_error")
        except RuntimeError, OSError:
            logger.info("connection already gone while failing its game", connection_id=connection.connection_id)
        except Exception:
            logger.exception("failed to close a connection of a failed game", connection_id=connection.connection_id)

    async def _finish_completed_game(
        self,
        game: Game,
        events: list[ServiceEvent],
        players: list[Player],
        replay_lines: list[str] | None,
    ) -> None:
        """
        Finish a completed game: save the replay, record the finish, close every socket with 1000.

        Runs in the path that claimed the game's end, right after its broadcast, on the replay lines and players
        detached there. An unexpected error saving the replay escalates the claim to a failure, which finishes the game
        with 1011. Once the finish record is written (best-effort) the completion stands: a socket whose close fails is
        logged and the next one is closed. The WebSocket disconnect handlers clean up session state when the connections
        close.
        """
        try:
            if self._replay_collector:
                await self._replay_collector.save(game.game_id, replay_lines)
        except Exception as exc:  # noqa: BLE001
            self._escalate_completion(game, exc=exc, replay_lines=replay_lines)
            return

        game_ended_event = next((e.data for e in events if isinstance(e.data, GameEndedEvent)), None)
        await self._record_game_finish(
            game_id=game.game_id,
            end_reason=GameEndReason.COMPLETED,
            game_ended_event=game_ended_event,
        )
        for player in players:
            await self._close_game_ended(player.connection)

    async def _close_game_ended(self, connection: ConnectionProtocol) -> None:
        try:
            await connection.close(code=1000, reason="game_ended")
        except RuntimeError, OSError:
            logger.info("connection already gone at game end", connection_id=connection.connection_id)
        except Exception:
            logger.exception("failed to close a connection at game end", connection_id=connection.connection_id)

    def _claim_completion(self, game: Game, events: list[ServiceEvent]) -> bool:
        """
        Claim the normal end of a game whose events end it, synchronously, before anything can suspend.

        Returns True when this call claimed it, which makes the caller the one path bound to finish the game; False when
        the events do not end the game or another path (a failure) already claimed its end.
        """
        if not self._has_game_ended(events) or game.ended or self._games.get(game.game_id) is not game:
            return False

        game.end_reason = GameEndReason.COMPLETED
        return True

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

    async def _handle_timeout(self, game_id: str, timeout_type: TimeoutType, seat: int, firing: TimerFiring) -> None:
        """
        Run a fired timer's default action; any unexpected error ends the game through fail_game.
        """
        game = self._games.get(game_id)
        if game is None:
            return

        try:
            await self._process_timeout(game, timeout_type=timeout_type, seat=seat, firing=firing)
        except Exception as exc:  # noqa: BLE001
            self.fail_game(game, reason=f"{timeout_type} timeout failed", exc=exc)

    async def _process_timeout(
        self,
        game: Game,
        *,
        timeout_type: TimeoutType,
        seat: int,
        firing: TimerFiring,
    ) -> None:
        game_id = game.game_id
        lock = self._get_game_lock(game_id)
        if lock is None:
            return

        offender_connection: ConnectionProtocol | None = None
        async with lock:
            superseded = self._timer_manager.is_superseded(game_id, seat, firing)
            if game.ended or self._games.get(game_id) is not game or superseded:
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
                events = await self._game_service.handle_timeout(
                    game_id=game_id, player_name=player.name, timeout_type=timeout_type
                )
            except InvalidGameActionError as e:
                offender_connection = await self._process_invalid_action(game, e)
            else:
                await self._broadcast_events(game, events)
                await self._maybe_start_timer(game, events)

        await self._close_offender_and_cleanup(offender_connection, game_id=game_id, game=game)
