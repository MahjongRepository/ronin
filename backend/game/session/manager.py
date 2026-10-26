import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from game.logic.enums import GameAction, GameErrorCode, TimeoutType, WaitKind
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    ErrorEvent,
    GameEndedEvent,
    GameStartedEvent,
    SeatTarget,
    ServiceEvent,
)
from game.logic.exceptions import InvalidGameActionError
from game.messaging.event_payload import (
    WAIT_ID_KEY,
    service_event_payload,
    shape_call_prompt_payload,
    stamp_timer_settings,
    stamp_viewer_seat,
    stamp_wait_id,
)
from game.messaging.types import (
    ErrorMessage,
    GameLeftMessage,
    PlayerLeftMessage,
    PlayerReconnectedMessage,
    SessionErrorCode,
    SessionMessageType,
    TimerSettings,
)
from game.session.models import GameLifecycle, GameSession, Participant
from game.session.played_game import build_finish_record
from game.session.replay_collector import ReplayRecord
from game.session.timer import TimerConfig, TurnTimer
from shared.dal.models import GameEndReason, PlayedGame, PlayedGameStanding
from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from game.logic.runtime import GameRuntime
    from game.logic.service import Awaiting, GameService
    from game.messaging.protocol import ConnectionProtocol
    from game.session.models import PlayerSpec
    from game.session.replay_collector import ReplayCollector
    from shared.dal.game_repository import GameRepository


logger = structlog.get_logger()


_AUTH_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class _Ending:
    """
    What a game's end claim detached for its finalizer: the reason, the connections to close, the replay to save.
    """

    reason: GameEndReason
    connections: list[ConnectionProtocol]
    replay_lines: list[str] | None
    game_ended_event: GameEndedEvent | None
    ended_at: datetime


class SessionManager:
    """
    The registry of live games and connections, and the transitions of each game's lifecycle.

    The registry holds only pending and playing games, their participants by game ticket, the registered connections and
    which participant each authenticated connection is bound to. A game's end is claimed once (`_end_game`), which
    releases it from the registry at once; its effects then run in one finalizer task the manager owns.
    """

    def __init__(
        self,
        game_service: GameService,
        *,
        game_repository: GameRepository,
        replay_collector: ReplayCollector,
        timer_config: TimerConfig | None = None,
    ) -> None:
        self._game_service = game_service
        self._game_repository = game_repository
        self._replay_collector = replay_collector
        self._timer_config = timer_config if timer_config is not None else TimerConfig()

        self._games: dict[str, GameSession] = {}
        self._participants_by_ticket: dict[str, Participant] = {}
        self._connections: dict[str, ConnectionProtocol] = {}
        self._bound: dict[str, Participant] = {}

        self._auth_timeouts: dict[str, asyncio.Task[None]] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """
        Start a background task the manager owns until it finishes; shutdown waits for it.
        """
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def register_connection(self, connection: ConnectionProtocol) -> None:
        self._connections[connection.connection_id] = connection
        self._auth_timeouts[connection.connection_id] = self._spawn(self._auth_timeout(connection))

    def unregister_connection(self, connection: ConnectionProtocol) -> None:
        self._evict_connection(connection)

    def _evict_connection(self, connection: ConnectionProtocol) -> None:
        """
        Drop a connection from the registry: no join, reconnect or action can pick it up afterwards.

        Every server-initiated close evicts first, so a message the client pipelined on the closing socket finds it
        unregistered. A participant still bound to it is left without a connection.
        """
        connection_id = connection.connection_id
        self._connections.pop(connection_id, None)
        self._cancel_auth_timeout(connection_id)
        participant = self._bound.pop(connection_id, None)
        if participant is not None:
            participant.connection = None

    def _bind(self, participant: Participant, connection: ConnectionProtocol) -> None:
        participant.connection = connection
        self._bound[connection.connection_id] = participant
        self._cancel_auth_timeout(connection.connection_id)

    def _unbind(self, participant: Participant, connection: ConnectionProtocol) -> None:
        self._bound.pop(connection.connection_id, None)
        participant.connection = None

    def get_game(self, game_id: str) -> GameSession | None:
        return self._games.get(game_id)

    def get_connection_game(self, connection: ConnectionProtocol) -> GameSession | None:
        """
        Return the game of the participant the connection is bound to, or None.
        """
        participant = self._bound.get(connection.connection_id)
        return participant.game if participant is not None else None

    @property
    def game_count(self) -> int:
        return len(self._games)

    @property
    def pending_game_count(self) -> int:
        return sum(1 for game in self._games.values() if game.lifecycle is GameLifecycle.PENDING)

    @property
    def started_game_count(self) -> int:
        """
        Count of games playing (pending games excluded).
        """
        return sum(1 for game in self._games.values() if game.lifecycle is GameLifecycle.PLAYING)

    def get_playing_game_id(self, user_id: str) -> str | None:
        """
        Return the id of the game the user is playing, or None.

        A user plays a game from its creation (pending included) until its end is claimed: a participant of theirs in a
        registered game counts, connected or not. A disconnected player keeps counting on purpose, so the lobby keeps
        them out of rooms and matchmaking until that game ends.
        """
        for game in self._games.values():
            if any(participant.user_id == user_id for participant in game.participants):
                return game.game_id

        return None

    def _send_error(self, connection: ConnectionProtocol, *, code: SessionErrorCode, message: str) -> None:
        logger.warning("session error sent to client", error_code=code.value, error_message=message)
        connection.send_message(ErrorMessage(code=code, message=message).model_dump())

    def create_pending_game(self, *, game_id: str, player_specs: list[PlayerSpec]) -> None:
        """
        Register a pending game, waiting for its players to connect via JOIN_GAME, with its pending timeout armed.
        """
        if game_id in self._games:
            raise ValueError(f"Game {game_id} already exists")

        game = GameSession(game_id=game_id, timer_config=self._timer_config)
        for spec in player_specs:
            participant = Participant(spec=spec, game=game, timer=TurnTimer(self._timer_config))
            game.participants.append(participant)
            self._participants_by_ticket[spec.game_ticket] = participant

        self._games[game_id] = game
        game.pending_timeout = self._spawn(self._pending_game_timeout(game))
        logger.info("pending game created", game_id=game_id, expected_count=len(player_specs))

    def join_game(self, connection: ConnectionProtocol, *, game_id: str, session_token: str) -> None:
        """
        Bind a connection to its participant in a pending game; the last expected join starts the game.

        A participant that already has a connection (a stale socket) is moved to the new one, and the old one is evicted
        and closed. A JOIN_GAME on a connection the server already evicted is dropped unanswered.
        """
        if self._connections.get(connection.connection_id) is not connection:
            return

        game = self._games.get(game_id)
        if game is None:
            self._send_error(connection, code=SessionErrorCode.JOIN_GAME_NOT_FOUND, message="Game not found")
            return

        participant = self._joining_participant(connection, game=game, session_token=session_token)
        if participant is None:
            return

        self._admit(game, participant, connection)

    def _joining_participant(
        self,
        connection: ConnectionProtocol,
        *,
        game: GameSession,
        session_token: str,
    ) -> Participant | None:
        """
        Return the participant a JOIN_GAME names, or None after answering why it cannot join.
        """
        if game.lifecycle is GameLifecycle.PLAYING:
            self._send_error(
                connection,
                code=SessionErrorCode.JOIN_GAME_ALREADY_STARTED,
                message="Game already started, use RECONNECT",
            )
            return None

        if connection.connection_id in self._bound:
            self._send_error(connection, code=SessionErrorCode.ALREADY_IN_GAME, message="Connection already in a game")
            return None

        participant = self._participants_by_ticket.get(session_token)
        if participant is None:
            self._send_error(
                connection, code=SessionErrorCode.JOIN_GAME_NO_SESSION, message="No session for this ticket"
            )
            return None

        if participant.game is not game:
            self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_GAME_MISMATCH,
                message="Session token is not valid for this game",
            )
            return None

        return participant

    def _admit(self, game: GameSession, participant: Participant, connection: ConnectionProtocol) -> None:
        """
        Bind the joining connection, replacing a stale one, and start the game once every participant is connected.
        """
        stale = participant.connection
        if stale is not None:
            logger.info(
                "evicting stale connection for duplicate JOIN_GAME",
                game_id=game.game_id,
                old_connection_id=stale.connection_id,
                new_connection_id=connection.connection_id,
            )
            self._evict_connection(stale)
            stale.close(code=1000, reason="replaced_by_new_connection")

        self._bind(participant, connection)
        connected = len(game.connected())
        logger.info(
            "player joined pending game",
            game_id=game.game_id,
            player_name=participant.name,
            connected=connected,
            expected=len(game.participants),
        )
        if connected < len(game.participants):
            return

        if game.pending_timeout is not None:
            game.pending_timeout.cancel()
            game.pending_timeout = None

        self._start_game(game)

    async def _pending_game_timeout(self, game: GameSession) -> None:
        """
        Start the pending game with AI players in the empty seats, or abandon it when nobody is connected.

        After its sleep the task detaches itself from the game, so the start or end it runs never cancels it. Every way
        out of PENDING cancels the task, even once its sleep ended, so it only ever runs on a pending game. Any
        unexpected error ends the game through fail_game.
        """
        await asyncio.sleep(game.timer_config.pending_game_timeout_seconds)

        game.pending_timeout = None
        try:
            if not game.connected():
                logger.warning(
                    "no players connected before timeout, cancelling game",
                    game_id=game.game_id,
                    expected=len(game.participants),
                )
                self._end_game(game, GameEndReason.ABANDONED)
                return

            self._start_game(game)
        except Exception as exc:  # noqa: BLE001
            self.fail_game(game, reason="pending game timeout failed", exc=exc)

    def _start_game(self, game: GameSession) -> None:
        """
        Start the engine game for every participant, connected or not, and show its start before the first deal.

        Each participant is bound to the seat the engine assigned to its spec (by input order, never by name). The game
        start goes out at once; the rest of the start's events, the first deal, follow after the game start pause, and
        the first wait's timers only with them, so showing the start eats no turn time. A zero pause deals at once.
        """
        game.lifecycle = GameLifecycle.PLAYING
        start = self._game_service.start_game(game.game_id, [participant.name for participant in game.participants])
        game.runtime = start.runtime
        for participant, seat in zip(game.participants, start.seats, strict=True):
            participant.seat = seat

        started_state = start.runtime.state
        game.replay = ReplayRecord(
            seed=started_state.seed,
            rng_version=started_state.rng_version,
            settings=started_state.settings,
        )
        self._record_game_start(game, start.runtime)
        logger.info("pending game completed", game_id=game.game_id)

        opening = [event for event in start.events if isinstance(event.data, GameStartedEvent)]
        deal = [event for event in start.events if not isinstance(event.data, GameStartedEvent)]
        self._send_events(game, opening, start.awaiting)
        if game.timer_config.game_start_pause_seconds > 0:
            game.start_pause = self._spawn(self._deal_after_start_pause(game, events=deal, awaiting=start.awaiting))
        else:
            self._deal_first_round(game, events=deal, awaiting=start.awaiting)

    async def _deal_after_start_pause(
        self, game: GameSession, *, events: list[ServiceEvent], awaiting: Awaiting
    ) -> None:
        """
        Deal the first round once the game start pause has passed.

        After its sleep the task detaches itself from the game (`start_pause`), so the deal and everything after it
        treat the game as dealt. Every end claim cancels the task, even once its sleep ended, so it only ever deals in a
        playing game. Any unexpected error ends the game through fail_game.
        """
        await asyncio.sleep(game.timer_config.game_start_pause_seconds)

        game.start_pause = None
        try:
            self._deal_first_round(game, events=events, awaiting=awaiting)
        except Exception as exc:  # noqa: BLE001
            self.fail_game(game, reason="first deal failed", exc=exc)

    def _deal_first_round(self, game: GameSession, *, events: list[ServiceEvent], awaiting: Awaiting) -> None:
        """
        Send the first deal and open the first wait; then seat an AI player for every participant without a connection.

        An absent participant (never joined, or left during the game start pause) can RECONNECT later.
        """
        absent = [participant for participant in game.participants if not participant.is_connected]
        self._follow_engine(game, events=events, awaiting=awaiting, actor=None)
        for participant in absent:
            if game.lifecycle is GameLifecycle.PLAYING:
                self._release_seat(participant)

    def _record_game_start(self, game: GameSession, runtime: GameRuntime) -> None:
        """
        Capture the game's start record and post it: every seat in seat order, each participant's user_id by seat.
        """
        game_state = runtime.state
        user_ids_by_seat = {participant.seat: participant.user_id for participant in game.participants}
        standings = [
            PlayedGameStanding(name=p.name, seat=p.seat, user_id=user_ids_by_seat.get(p.seat, ""))
            for p in game_state.round_state.players
        ]
        game.start_record = PlayedGame(
            game_id=game.game_id,
            started_at=datetime.now(UTC),
            game_type=game_state.settings.game_type,
            standings=standings,
        )
        self._game_repository.create_game(game.start_record)

    def leave_game(self, connection: ConnectionProtocol, *, notify_player: bool = True) -> None:
        """
        Take a closed connection's participant out of its game.

        In a pending game the participant waits for a new JOIN_GAME (the pending timeout handles an empty game). In a
        playing game an AI player takes the seat, or, when nobody connected remains, the game is abandoned.
        """
        participant = self._bound.get(connection.connection_id)
        if participant is None:
            return

        game = participant.game
        logger.info("player left game")
        self._unbind(participant, connection)
        if notify_player:
            connection.send_message(GameLeftMessage().model_dump())

        self._broadcast_to_game(game, PlayerLeftMessage(player_name=participant.name).model_dump())
        if game.lifecycle is GameLifecycle.PLAYING:
            self._release_seat(participant)

    def _release_seat(self, participant: Participant) -> None:
        """
        Hand a participant's seat to an AI player, which plays any turn or call it owed.

        The participant's timer stops, deducting the bank it used. When no connected participant remains the game is
        abandoned instead: there are never all-AI games. During the game start pause the seat stays empty: the first
        deal hands it over, so no AI player's move goes out ahead of the deal.
        """
        game = participant.game
        participant.timer.stop()
        if not game.connected():
            self._end_game(game, GameEndReason.ABANDONED)
            return

        if game.start_pause is not None:
            return

        seat = self._seat_of(participant)
        runtime = self._runtime_of(game)
        self._game_service.replace_with_ai_player(runtime, seat)
        update = self._game_service.process_ai_player_actions_after_replacement(runtime, seat)
        self._follow_engine(game, events=update.events, awaiting=update.awaiting, actor=seat)

    def _kick_player(
        self,
        participant: Participant,
        connection: ConnectionProtocol,
        error: InvalidGameActionError,
    ) -> None:
        """
        Disconnect a human who sent structurally impossible input for their own seat with 1008, and seat an AI player.

        The connection leaves the registry first, so a RECONNECT pipelined on the closing socket is dropped. An error
        while replacing the player propagates before the close: it is a server fault the caller's boundary turns into
        fail_game, which closes the connection with 1011.
        """
        logger.warning("invalid game action", action=error.action, reason=error.reason)
        self._evict_connection(connection)
        self._broadcast_to_game(participant.game, PlayerLeftMessage(player_name=participant.name).model_dump())
        self._release_seat(participant)
        connection.close(code=1008, reason="invalid_game_action")

    def handle_game_action(
        self,
        connection: ConnectionProtocol,
        *,
        action: GameAction,
        data: dict[str, Any],
        wait_id: int,
    ) -> None:
        """
        Run a player's game action.

        An action whose wait id is not the current wait's answers to a wait that already ended (it raced its own timeout
        or a newer prompt): the seat gets a `stale_action` ErrorEvent, and neither the engine nor a timer is touched. A
        rule judgment or race comes back from the engine as an ErrorEvent for the seat. Structurally impossible input
        (InvalidGameActionError, always the acting seat's) disconnects the player with 1008 and seats an AI player.
        Anything else the engine raises is a server fault and propagates to the caller's boundary, which fails the game.
        """
        participant = self._bound_participant(connection)
        if participant is None:
            return

        game = participant.game
        if game.lifecycle is GameLifecycle.PENDING:
            self._send_error(connection, code=SessionErrorCode.GAME_NOT_STARTED, message="Game has not started yet")
            return

        seat = self._seat_of(participant)
        structlog.contextvars.bind_contextvars(seat=seat)
        if game.awaiting is None or wait_id != game.awaiting.wait_id:
            self._send_stale_action(connection, seat=seat, action=action, wait_id=wait_id)
            return

        try:
            update = self._game_service.handle_action(self._runtime_of(game), seat=seat, action=action, data=data)
        except InvalidGameActionError as e:
            self._kick_player(participant, connection, error=e)
            return

        self._follow_engine(game, events=update.events, awaiting=update.awaiting, actor=seat)

    def _bound_participant(self, connection: ConnectionProtocol) -> Participant | None:
        """
        Return the participant a game message's connection is bound to, or None after answering `not_in_game`.

        A connection the server evicted (its game ended, or it was kicked) gets no answer: its close is queued, or for a
        game end follows from the finalizer, and a `not_in_game` ahead of it would read as a permanent error to a client
        still showing the game's end.
        """
        participant = self._bound.get(connection.connection_id)
        if participant is None and self._connections.get(connection.connection_id) is connection:
            self._send_error(connection, code=SessionErrorCode.NOT_IN_GAME, message="You must join a game first")

        return participant

    def _send_stale_action(
        self,
        connection: ConnectionProtocol,
        *,
        seat: int,
        action: GameAction,
        wait_id: int,
    ) -> None:
        """
        Answer an action for a wait that already ended with a `stale_action` ErrorEvent to its seat.
        """
        logger.info("stale game action", action=action.value, wait_id=wait_id)
        error = ErrorEvent(
            code=GameErrorCode.STALE_ACTION,
            message="the wait this action answers has already ended",
            target=SeatTarget(seat=seat),
        )
        connection.send_message(service_event_payload(ServiceEvent(data=error)))

    def reconnect(self, connection: ConnectionProtocol, *, game_id: str, session_token: str) -> None:
        """
        Bind a new connection to a disconnected participant of a playing game and send it the game's state.

        Take the seat back from the AI player (`restore_human_player`), send the `game_reconnected` snapshot with the
        current wait id and the seat's timer settings (its bank as of its last turn), broadcast `player_reconnected`,
        and, when the game awaits that seat's turn, re-send its draw and start its turn timer. A RECONNECT on a
        connection the server already evicted is dropped unanswered.
        """
        if self._connections.get(connection.connection_id) is not connection:
            return

        participant = self._reconnecting_participant(connection, game_id=game_id, session_token=session_token)
        if participant is None:
            return

        game = participant.game
        seat = self._seat_of(participant)
        runtime = self._runtime_of(game)
        self._game_service.restore_human_player(runtime, seat)
        snapshot = self._game_service.build_reconnection_snapshot(runtime, seat)
        self._bind(participant, connection)
        awaiting = self._game_service.get_awaiting(runtime)
        game.awaiting = awaiting
        payload = snapshot.model_dump(by_alias=True, exclude_none=True)
        payload["type"] = SessionMessageType.GAME_RECONNECTED
        payload[WAIT_ID_KEY] = awaiting.wait_id
        connection.send_message(stamp_timer_settings(payload, self._timer_settings(participant)))

        self._broadcast_to_game(
            game,
            PlayerReconnectedMessage(player_name=participant.name).model_dump(),
            exclude=connection,
        )
        self._send_turn_state_on_reconnect(participant, connection, awaiting=awaiting)

        structlog.contextvars.bind_contextvars(seat=seat)
        logger.info("player reconnected")

    def _reconnecting_participant(
        self,
        connection: ConnectionProtocol,
        *,
        game_id: str,
        session_token: str,
    ) -> Participant | None:
        """
        Return the participant a RECONNECT names, or None after answering why it cannot reconnect (yet).

        A game that has not dealt its first round (pending, or in its game start pause), or a participant whose old
        connection the server has not seen drop yet, answers retry later: the client retries.
        """
        participant = self._participants_by_ticket.get(session_token)
        if participant is None:
            self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_NO_SESSION,
                message="No disconnected session found",
            )
            return None

        if participant.game.game_id != game_id:
            self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_GAME_MISMATCH,
                message="Session token is not valid for this game",
            )
            return None

        if participant.game.lifecycle is GameLifecycle.PENDING or participant.game.start_pause is not None:
            self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_RETRY_LATER,
                message="Game has not started yet, retry shortly",
            )
            return None

        if participant.is_connected:
            self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_RETRY_LATER,
                message="Session not yet disconnected, retry shortly",
            )
            return None

        if connection.connection_id in self._bound:
            self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_ALREADY_ACTIVE,
                message="Connection already in a game",
            )
            return None

        return participant

    def _send_turn_state_on_reconnect(
        self,
        participant: Participant,
        connection: ConnectionProtocol,
        *,
        awaiting: Awaiting,
    ) -> None:
        """
        Re-send the event that opened the turn (the draw, or the turn event after the seat's own pon or chi) and start
        the turn timer for a reconnected participant whose turn the game awaits.

        Sent directly instead of through `_send_events`, so the replay does not record the draw twice.
        """
        seat = self._seat_of(participant)
        if awaiting.kind != WaitKind.TURN or seat not in awaiting.seats:
            return

        for event in self._game_service.build_turn_event_for_seat(self._runtime_of(participant.game), seat):
            connection.send_message(stamp_wait_id(service_event_payload(event), event, awaiting))

        self._start_turn_timer(participant)

    def _follow_engine(
        self,
        game: GameSession,
        *,
        events: list[ServiceEvent],
        awaiting: Awaiting,
        actor: int | None,
    ) -> None:
        """
        Deliver an engine call's events and drive the timers from the wait it reports.

        The call's actor is the seat that acted, timed out or was replaced; a game start has none. When the wait id
        changed, the actor's timer stops (deducting its bank on a turn) and every other timer is cancelled before the
        events go out, and the new wait's timers start after them. When it did not, only an actor that left the wait (a
        partial prompt response or confirmation) has its timer stopped; an actor still awaited (an error) keeps it
        running with nothing deducted.
        """
        previous = game.awaiting
        game.awaiting = awaiting
        new_wait = previous is None or awaiting.wait_id != previous.wait_id
        if new_wait:
            self._end_wait_timers(game, actor=actor)
        elif actor is not None and actor in previous.seats and actor not in awaiting.seats:
            self._stop_timer_at(game, actor)

        self._broadcast_events(game, events, awaiting)
        if new_wait and game.lifecycle is GameLifecycle.PLAYING:
            self._start_wait_timers(game, previous=previous, awaiting=awaiting)

    @staticmethod
    def _end_wait_timers(game: GameSession, *, actor: int | None) -> None:
        """
        Stop the actor's timer and cancel the others when a wait ended.
        """
        for participant in game.participants:
            if actor is not None and participant.seat == actor:
                participant.timer.stop()
            else:
                participant.timer.cancel()

    @staticmethod
    def _stop_timer_at(game: GameSession, seat: int) -> None:
        participant = game.at_seat(seat)
        if participant is not None:
            participant.timer.stop()

    def _start_wait_timers(self, game: GameSession, *, previous: Awaiting | None, awaiting: Awaiting) -> None:
        """
        Start the timers of a new wait for its awaited seats that have a connected participant.

        The first wait of a round adds the round bonus to every connected participant's bank, the first round included.
        """
        connected = sorted(game.connected(), key=self._seat_of)
        if previous is None or awaiting.round_number != previous.round_number:
            for participant in connected:
                participant.timer.add_round_bonus()

        if awaiting.kind == WaitKind.ROUND_ADVANCE:
            for participant in connected:
                self._start_round_advance_timer(participant, results_shown=awaiting.results_shown)

            return

        for participant in connected:
            if participant.seat not in awaiting.seats:
                continue

            if awaiting.kind == WaitKind.TURN:
                self._start_turn_timer(participant)
            else:
                self._start_meld_timer(participant)

    def _start_turn_timer(self, participant: Participant) -> None:
        participant.timer.start_turn_timer(lambda: self._handle_timeout(participant, TimeoutType.TURN))

    def _start_meld_timer(self, participant: Participant) -> None:
        participant.timer.start_meld_timer(lambda: self._handle_timeout(participant, TimeoutType.MELD))

    def _start_round_advance_timer(self, participant: Participant, *, results_shown: int) -> None:
        """
        Start the round advance timer: the round advance timeout once for each result the round end shows in turn.
        """
        participant.timer.start_fixed_timer(
            participant.game.timer_config.round_advance_timeout_seconds * results_shown,
            lambda: self._handle_timeout(participant, TimeoutType.ROUND_ADVANCE),
        )

    def _broadcast_events(self, game: GameSession, events: list[ServiceEvent], awaiting: Awaiting) -> None:
        """
        Send an engine call's events; after a batch with which the game waits for nothing, claim its completion.

        Nothing between the sends and the claim can suspend, and the game end is queued to every socket before the
        finalizer queues its close. If a send raises (an encoding error), nothing was claimed and the caller's boundary
        fails the game.
        """
        self._send_events(game, events, awaiting)
        if awaiting.kind == WaitKind.NONE:
            game_ended_event = next((e.data for e in events if isinstance(e.data, GameEndedEvent)), None)
            self._end_game(game, GameEndReason.COMPLETED, game_ended_event=game_ended_event)

    def _send_events(self, game: GameSession, events: list[ServiceEvent], awaiting: Awaiting) -> None:
        """
        Record the events for the replay, then send each to its target, the wait's opening messages stamped with `wi`.

        `game_started` is broadcast as one copy per seat, each stamped with its recipient's own seat (`s`).
        """
        if game.replay is not None:
            self._replay_collector.collect_events(game.replay, events)

        for event in events:
            message = service_event_payload(event)
            if isinstance(event.data, CallPromptEvent):
                message = shape_call_prompt_payload(message)

            message = stamp_wait_id(message, event, awaiting)
            if isinstance(event.data, GameStartedEvent):
                self._send_to_each_seat(game, message)
            elif isinstance(event.target, BroadcastTarget):
                self._broadcast_to_game(game, message)
            elif isinstance(event.target, SeatTarget):
                participant = game.at_seat(event.target.seat)
                if participant is not None and participant.connection is not None:
                    participant.connection.send_message(message)

    def _send_to_each_seat(self, game: GameSession, message: dict[str, Any]) -> None:
        """
        Send a broadcast message to every connected participant, each copy stamped with its recipient's seat and timer
        settings.
        """
        for participant in game.participants:
            if participant.connection is not None:
                stamped = stamp_viewer_seat(message, self._seat_of(participant))
                participant.connection.send_message(stamp_timer_settings(stamped, self._timer_settings(participant)))

    @staticmethod
    def _timer_settings(participant: Participant) -> TimerSettings:
        config = participant.game.timer_config
        return TimerSettings(
            base_turn_seconds=config.base_turn_seconds,
            bank_seconds=participant.timer.bank_seconds,
            round_bonus_seconds=config.round_bonus_seconds,
            max_bank_seconds=config.max_bank_seconds,
            meld_decision_seconds=config.meld_decision_seconds,
        )

    @staticmethod
    def _broadcast_to_game(
        game: GameSession,
        message: dict[str, Any],
        exclude: ConnectionProtocol | None = None,
    ) -> None:
        """
        Send a message to every connected participant of the game, skipping one connection if excluded.
        """
        for participant in game.participants:
            connection = participant.connection
            if connection is not None and connection is not exclude:
                connection.send_message(message)

    @staticmethod
    def _seat_of(participant: Participant) -> int:
        """
        Return the seat of a participant in a started game, where every participant is bound to one.
        """
        if participant.seat is None:
            raise AssertionError("participant in a started game has no seat")

        return participant.seat

    @staticmethod
    def _runtime_of(game: GameSession) -> GameRuntime:
        """
        Return the engine runtime of a playing game, which holds it from the start until its end claim drops it.
        """
        if game.runtime is None:
            raise AssertionError("engine call on a game without a runtime")

        return game.runtime

    def _handle_timeout(self, participant: Participant, timeout_type: TimeoutType) -> None:
        """
        Run a fired timer's default action; any unexpected error ends the game through fail_game.

        It needs no guard: every path that ends the game, ends the wait or releases the seat cancels the timer, and a
        cancel after its sleep ended still stops it before this runs.
        """
        game = participant.game
        try:
            seat = self._seat_of(participant)
            update = self._game_service.handle_timeout(self._runtime_of(game), seat=seat, timeout_type=timeout_type)
            self._follow_engine(game, events=update.events, awaiting=update.awaiting, actor=seat)
        except Exception as exc:  # noqa: BLE001
            self.fail_game(game, reason=f"{timeout_type} timeout failed", exc=exc)

    def _end_game(
        self,
        game: GameSession,
        reason: GameEndReason,
        *,
        game_ended_event: GameEndedEvent | None = None,
    ) -> bool:
        """
        Claim a game's end and release it, synchronously, then hand its effects to one owned finalizer.

        Only a pending or playing game can be claimed: the claimer gets True, every later caller False. The claim first
        detaches the connected participants' connections and the replay lines (an abandoned game's replay is discarded)
        and spawns the finalizer on them, so a release step that raised would still leave the game finished. It then
        drops the game and its tickets from the registry, cancels the pending timeout, the game start pause and every
        sleeping timer, evicts the detached connections and drops the engine runtime. The finalizer saves the replay,
        posts the finish record and closes the detached connections (1000 for a completion, `internal_error` and 1011
        for a failure).
        """
        if not game.is_active:
            return False

        game.lifecycle = GameLifecycle.ENDING
        connections = [participant.connection for participant in game.participants if participant.connection]
        replay_lines = game.replay.lines if game.replay is not None and reason != GameEndReason.ABANDONED else None
        game.replay = None
        self._spawn(
            self._finish_game(
                game,
                _Ending(
                    reason=reason,
                    connections=connections,
                    replay_lines=replay_lines,
                    game_ended_event=game_ended_event,
                    ended_at=datetime.now(UTC),
                ),
            ),
        )

        self._games.pop(game.game_id, None)
        for participant in game.participants:
            if self._participants_by_ticket.get(participant.ticket) is participant:
                del self._participants_by_ticket[participant.ticket]

            participant.timer.cancel()

        for task in (game.pending_timeout, game.start_pause):
            if task is not None:
                task.cancel()

        game.pending_timeout = None
        game.start_pause = None
        for connection in connections:
            self._evict_connection(connection)

        game.runtime = None
        return True

    async def _finish_game(self, game: GameSession, ending: _Ending) -> None:
        """
        Run the effects of a game's end on what the claim detached: replay, finish record, closes.

        Each step is its own error boundary: an unexpected failure is logged and the steps after it, down to the last
        close, still run. Any error saving a completed game's replay, storage errors included, turns its end into a
        failure. A game with no start record (it never started) records no finish.
        """
        game_id = game.game_id
        end_reason = ending.reason
        if ending.replay_lines is not None:
            try:
                await self._replay_collector.save(game_id, ending.replay_lines)
            except Exception:
                logger.exception("failed to save the replay of a finished game", game_id=game_id)
                end_reason = GameEndReason.ERROR

        try:
            self._record_game_finish(
                game,
                end_reason=end_reason,
                ended_at=ending.ended_at,
                game_ended_event=ending.game_ended_event if end_reason == GameEndReason.COMPLETED else None,
            )
        except Exception:
            logger.exception("failed to record the finish of a game", game_id=game_id)

        for connection in ending.connections:
            if end_reason == GameEndReason.COMPLETED:
                self._close_game_ended(connection)
            else:
                self._close_with_internal_error(connection)

        game.lifecycle = GameLifecycle.CLOSED

    def _record_game_finish(
        self,
        game: GameSession,
        *,
        end_reason: GameEndReason,
        ended_at: datetime,
        game_ended_event: GameEndedEvent | None,
    ) -> None:
        if game.start_record is None:
            return

        self._game_repository.finish_game(
            build_finish_record(
                game.start_record,
                end_reason=end_reason,
                ended_at=ended_at,
                game_ended_event=game_ended_event,
            ),
        )

    def fail_game(self, game: GameSession, *, reason: str, exc: BaseException | None = None) -> bool:
        """
        End a game on a server fault: the one terminal path for one, idempotent and callable from any context.

        It claims the game's end as ERROR (`_end_game`) synchronously, so a later action, timeout, join or reconnect
        finds no game. The finalizer records the error end, saves whatever replay history exists, and sends every
        connected participant an `internal_error` session error before closing with 1011. The current task is never
        cancelled or awaited.

        Returns True when this call ended the game; False when its end was already claimed. Either way the caller skips
        its normal broadcast and timers.
        """
        logger.error("game failed", game_id=game.game_id, reason=reason, exc_info=exc)
        return self._end_game(game, GameEndReason.ERROR)

    def fail_connection(
        self,
        connection: ConnectionProtocol,
        game: GameSession | None,
        *,
        reason: str,
        exc: Exception,
    ) -> None:
        """
        Handle a server fault met while serving a connection's message or disconnect.

        With a game (the one the connection was acting in, captured before the failing call), the game ends through
        fail_game, whose finalizer closes its connected participants; the connection itself is evicted from the registry
        and closed with 1011 here when it is not among them (a join or reconnect that failed before binding it, a
        participant already gone). With no game there is nothing to fail: the fault is logged with its traceback, and
        the connection evicted and closed with 1011. The eviction comes first, so a JOIN_GAME or RECONNECT pipelined
        behind the failed message is dropped.
        """
        seated = game is not None and any(participant.connection is connection for participant in game.participants)
        if game is not None:
            self.fail_game(game, reason=reason, exc=exc)
        else:
            logger.error("connection failed outside a game", reason=reason, exc_info=exc)

        if not seated:
            self._evict_connection(connection)
            self._close_with_internal_error(connection)

    @staticmethod
    def _close_game_ended(connection: ConnectionProtocol) -> None:
        try:
            connection.close(code=1000, reason="game_ended")
        except Exception:
            logger.exception("failed to close a connection of a finished game", connection_id=connection.connection_id)

    def _close_with_internal_error(self, connection: ConnectionProtocol) -> None:
        message = ErrorMessage(code=SessionErrorCode.INTERNAL_ERROR, message="The game ended on a server error")
        try:
            try:
                connection.send_message(message.model_dump())
            finally:
                connection.close(code=1011, reason="internal_error")
        except Exception:
            logger.exception("failed to close a connection of a failed game", connection_id=connection.connection_id)

    async def shutdown(self) -> None:
        """
        Stop every background task before the server's resources close.

        Sleeping pending, game start pause, auth and turn timers are cancelled, all in one step, so none of them can
        fire and end a game meanwhile; the games' finalizers are awaited, so their replay saves, finish record posts and
        socket closes happen first. Games still running are not recorded as ended.
        """
        sleeping = [
            task
            for game in self._games.values()
            for task in (game.pending_timeout, game.start_pause)
            if task is not None
        ]
        sleeping.extend(
            participant.timer.task
            for game in self._games.values()
            for participant in game.participants
            if participant.timer.task is not None
        )
        sleeping.extend(self._auth_timeouts.values())
        self._auth_timeouts.clear()
        await cancel_and_wait(sleeping, finalizing=list(self._background_tasks))

    def _cancel_auth_timeout(self, connection_id: str) -> None:
        task = self._auth_timeouts.pop(connection_id, None)
        if task is not None:
            task.cancel()

    async def _auth_timeout(self, connection: ConnectionProtocol) -> None:
        """
        Close an unauthenticated connection after a timeout.

        The task detaches itself from `_auth_timeouts` after its sleep, so cancel paths leave the close alone. Binding
        or evicting the connection cancels it, even once its sleep ended, so it only ever closes a registered connection
        that never authenticated. An unexpected error is logged and the connection closed with 1011: there is no game to
        fail yet.
        """
        await asyncio.sleep(_AUTH_TIMEOUT_SECONDS)

        self._auth_timeouts.pop(connection.connection_id, None)
        try:
            self._close_unauthenticated(connection)
        except Exception:
            logger.exception("auth timeout failed", connection_id=connection.connection_id)
            connection.close(code=1011, reason="internal_error")

    def _close_unauthenticated(self, connection: ConnectionProtocol) -> None:
        self._evict_connection(connection)
        logger.info("auth timeout, closing unauthenticated connection", connection_id=connection.connection_id)
        connection.close(code=4001, reason="auth_timeout")
