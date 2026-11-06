import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from game.logic.enums import GameAction, GameErrorCode, TimeoutType, WaitKind
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    DrawEvent,
    ErrorEvent,
    GameEndedEvent,
    GameEvent,
    GameStartedEvent,
    RoundStartedEvent,
    SeatTarget,
)
from game.logic.exceptions import InvalidGameActionError
from game.messaging.event_payload import (
    draw_notice_payload,
    game_event_payload,
    live_game_event_payload,
    reconnection_payload,
    shape_call_prompt_payload,
    stamp_timer_settings,
    stamp_viewer_seat,
    stamp_wait_id,
)
from game.messaging.types import (
    ErrorMessage,
    GameJoinedMessage,
    SeatControlMessage,
    SessionErrorCode,
    SessionMessageType,
    TimerSettings,
)
from game.session.models import GameLifecycle, GameSession, Participant
from game.session.played_game import build_finish_record
from game.session.replay_collector import ReplayRecord
from game.session.timer import TimerConfig, TurnTimer
from game.wire.enums import SeatControlReason
from game.wire.keys import WireKey
from shared.auth.game_ticket import TICKET_TTL_SECONDS
from shared.dal.models import GameEndReason, PlayedGame, PlayedGameStanding
from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

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
    replay_records: list[dict[int, object]] | None
    game_ended_event: GameEndedEvent | None
    ended_at: datetime


def _naming_wait(event: GameEvent, *, wait_id: int) -> GameEvent:
    """
    Return an engine event of a player's action, an ErrorEvent refusing it named by the wait id the action echoed.
    """
    return event.model_copy(update={"wait_id": wait_id}) if isinstance(event, ErrorEvent) else event


class SessionManager:
    """
    The registry of live games and connections, and the transitions of each game's lifecycle.

    The registry holds only pending and playing games, their participants by game ticket, the registered connections and
    which participant each authenticated connection is bound to. A game's end is claimed once (`_end_game`), which
    releases it from the registry at once; its effects then run in one finalizer task the manager owns. Every monotonic
    time it reads comes from its clock, the participants' turn timers (`TurnTimer`) included.
    """

    def __init__(
        self,
        game_service: GameService,
        *,
        game_repository: GameRepository,
        replay_collector: ReplayCollector,
        timer_config: TimerConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._game_service = game_service
        self._game_repository = game_repository
        self._replay_collector = replay_collector
        self._timer_config = timer_config if timer_config is not None else TimerConfig()
        self._clock = clock

        self._games: dict[str, GameSession] = {}
        self._withdrawn_game_ids: dict[str, float] = {}
        self._participants_by_ticket: dict[str, Participant] = {}
        self._connections: dict[str, ConnectionProtocol] = {}
        self._bound: dict[str, Participant] = {}

        self._auth_timeouts: dict[str, asyncio.Task[None]] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()

        self._reconnects = 0
        self._takeovers = 0
        self._resyncs = 0
        self._timeouts = dict.fromkeys(TimeoutType, 0)
        self._ai_replacements = 0

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
        """
        Bind a connection to its participant, replacing the connection the participant still has.

        The replaced connection is evicted before its close, so its late
        messages and its disconnect touch no one, and closed with 4002
        `replaced_by_new_connection`, which tells its client to stop
        reconnecting: two live clients of one participant would
        otherwise take the seat back from each other forever. Its timer
        is the participant's, so a replacement leaves it running.
        """
        replaced = participant.connection
        if replaced is not None:
            logger.info(
                "replacing a participant's connection",
                old_connection_id=replaced.connection_id,
                new_connection_id=connection.connection_id,
            )
            self._evict_connection(replaced)
            replaced.close(code=4002, reason="replaced_by_new_connection")
            self._takeovers += 1

        participant.connection = connection
        self._bound[connection.connection_id] = participant
        self._cancel_auth_timeout(connection.connection_id)

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

    @property
    def stats(self) -> dict[str, int]:
        """
        Return the session event totals since the manager was created, process-wide and never per user.
        """
        return {
            "reconnects": self._reconnects,
            "takeovers": self._takeovers,
            "resyncs": self._resyncs,
            **{f"timeouts_{timeout_type}": count for timeout_type, count in self._timeouts.items()},
            "ai_replacements": self._ai_replacements,
        }

    def get_playing_participant(self, user_id: str) -> Participant | None:
        """
        Return the user's participant in the game they are playing, or None.

        A user plays a game from its creation (pending included) until
        its end is claimed: a participant of theirs in a registered game
        counts, connected or not. A disconnected player keeps counting
        on purpose, so the lobby keeps them out of rooms and matchmaking
        until that game ends, and can hand them back the participant's
        own ticket.
        """
        for game in self._games.values():
            for participant in game.participants:
                if participant.user_id == user_id:
                    return participant

        return None

    def get_playing_game_id(self, user_id: str) -> str | None:
        """
        Return the id of the game the user is playing (`get_playing_participant`), or None.
        """
        participant = self.get_playing_participant(user_id)
        return participant.game.game_id if participant is not None else None

    def _send_error(self, connection: ConnectionProtocol, *, code: SessionErrorCode, message: str) -> None:
        logger.warning("session error sent to client", error_code=code.value, error_message=message)
        connection.send_message(ErrorMessage(code=code, message=message).payload())

    def create_pending_game(self, *, game_id: str, player_specs: list[PlayerSpec]) -> None:
        """
        Register a pending game, waiting for its players to connect via JOIN_GAME, with its pending timeout armed.
        """
        if game_id in self._games:
            raise ValueError(f"Game {game_id} already exists")

        if game_id in self._withdrawn_game_ids:
            raise ValueError(f"Game {game_id} was withdrawn")

        game = GameSession(game_id=game_id, timer_config=self._timer_config)
        for spec in player_specs:
            participant = Participant(spec=spec, game=game, timer=TurnTimer(self._timer_config, clock=self._clock))
            game.participants.append(participant)
            self._participants_by_ticket[spec.game_ticket] = participant

        self._games[game_id] = game
        game.pending_timeout = self._spawn(self._pending_game_timeout(game))
        logger.info("pending game created", game_id=game_id, expected_count=len(player_specs))

    def withdraw_game(self, game_id: str) -> bool:
        """
        Drop a game its creator gave up on, whether or not its creation has arrived; return False when it is kept.

        A pending game nobody has joined is abandoned at once, and the
        id is refused from then on, so a creation that arrives after the
        withdrawal never registers. Withdrawn ids are kept for as long
        as a game ticket lives: an older creation fails its ticket check
        anyway. A game someone joined, or one already playing, is kept.
        """
        now = self._clock()
        self._withdrawn_game_ids = {
            withdrawn_id: expires_at
            for withdrawn_id, expires_at in self._withdrawn_game_ids.items()
            if expires_at > now
        }

        game = self._games.get(game_id)
        if game is not None and (game.lifecycle is not GameLifecycle.PENDING or game.connected()):
            logger.warning("withdrawn game kept, a player already joined it", game_id=game_id)
            return False

        self._withdrawn_game_ids[game_id] = now + TICKET_TTL_SECONDS
        if game is not None:
            logger.info("pending game withdrawn", game_id=game_id)
            self._end_game(game, GameEndReason.ABANDONED)

        return True

    def join_game(self, connection: ConnectionProtocol, *, session_token: str) -> None:
        """
        Bind a connection to its participant in the connection's pending game; the last expected join starts the game.

        A participant that already has a connection (a stale socket or another client) is moved to the new one, and the
        old one is replaced (`_bind`). A JOIN_GAME on a connection the server already evicted is dropped unanswered.
        """
        if self._connections.get(connection.connection_id) is not connection:
            return

        game = self._games.get(connection.game_id)
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
        Bind the joining connection, replacing any the participant has, tell it it joined, and start the game once every
        participant is connected.
        """
        structlog.contextvars.bind_contextvars(game_id=game.game_id)
        self._bind(participant, connection)
        joined = GameJoinedMessage(pending_game_timeout_seconds=game.timer_config.pending_game_timeout_seconds)
        connection.send_message(joined.payload())
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

        structlog.contextvars.bind_contextvars(game_id=game.game_id)
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
        Start the engine game for every participant, connected or not, and open its first wait.

        Each participant is bound to the seat the engine assigned to its spec (by input order, never by name). With a
        game start confirmation timeout the engine stops after the deal on a round advance that starts the game, so the
        client shows the start over the dealt table until every seat confirmed or the timeout confirmed for it, and the
        dealer draws only then; a zero timeout lets the dealer draw at once.
        """
        game.lifecycle = GameLifecycle.PLAYING
        start = self._game_service.start_game(
            game.game_id,
            [participant.name for participant in game.participants],
            confirm_start=game.timer_config.game_start_confirm_seconds > 0,
        )
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
        self._open_first_wait(game, events=start.events, awaiting=start.awaiting)

    def _open_first_wait(self, game: GameSession, *, events: list[GameEvent], awaiting: Awaiting) -> None:
        """
        Send the start's events and open the first wait, with an AI player in the seat of every participant without a
        connection (never joined), who can RECONNECT later.

        The game start and the deal open the wait, so a round advance that starts the game stamps the deal of each
        awaited seat. Each absent seat is an AI player's from then on, so its line is recorded after the deal and ahead
        of the dealer's draw, the moves of the AI players seated from the start included; its AI player then confirms
        the start for it, or plays the turn or call the start leaves it.
        """
        runtime = self._runtime_of(game)
        dealt: list[GameEvent] = [event for event in events if isinstance(event, GameStartedEvent | RoundStartedEvent)]
        self._apply_engine_update(game, events=dealt, awaiting=awaiting, actor=None)

        absent = [participant for participant in game.participants if not participant.is_connected]
        for participant in absent:
            self._game_service.replace_with_ai_player(runtime, self._seat_of(participant))
            self._hand_over_seat(participant, stand_in=SeatControlReason.ABSENT)

        after_deal = [event for event in events if not isinstance(event, GameStartedEvent | RoundStartedEvent)]
        self._follow_engine(game, events=after_deal, awaiting=awaiting, actor=None)
        for participant in absent:
            if game.lifecycle is not GameLifecycle.PLAYING:
                return

            seat = self._seat_of(participant)
            update = self._game_service.process_ai_player_actions_after_replacement(runtime, seat)
            self._follow_engine(game, events=update.events, awaiting=update.awaiting, actor=seat)

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

    def disconnect(self, connection: ConnectionProtocol) -> None:
        """
        Evict a connection and take the participant bound to it out of its game.

        The eviction comes first and also cancels the auth timeout of a connection that never authenticated. The
        participant is the one bound to this connection, so the late disconnect of a connection the server already
        evicted or replaced touches no one. In a pending game the participant then waits for a new JOIN_GAME (the
        pending timeout handles an empty game), and in a playing game an AI player takes the seat, or, when nobody
        connected remains, the game is abandoned.
        """
        participant = self._bound.get(connection.connection_id)
        self._evict_connection(connection)
        if participant is None:
            return

        game = participant.game
        logger.info("player left game")
        if game.lifecycle is GameLifecycle.PLAYING:
            self._release_seat(participant)

    def _release_seat(self, participant: Participant) -> None:
        """
        Hand a departed participant's seat to an AI player, which answers any call or confirmation it owed at once and
        plays a turn it owed after the AI turn delay, and announce the handover (`_hand_over_seat`) ahead of the AI
        player's moves, once the engine made them.

        The participant's timer stops, deducting the bank it used. When no connected participant remains the game is
        abandoned instead: there are never all-AI games. During the game start confirmation the AI player confirms for
        the seat, so the others are not held to its timeout.
        """
        game = participant.game
        participant.timer.stop()
        if not game.connected():
            self._end_game(game, GameEndReason.ABANDONED)
            return

        seat = self._seat_of(participant)
        runtime = self._runtime_of(game)
        self._game_service.replace_with_ai_player(runtime, seat)
        update = self._game_service.process_ai_player_actions_after_replacement(runtime, seat)
        self._hand_over_seat(participant, stand_in=SeatControlReason.LEFT)
        self._follow_engine(game, events=update.events, awaiting=update.awaiting, actor=seat)

    def _hand_over_seat(self, participant: Participant, *, stand_in: SeatControlReason | None) -> None:
        """
        Record who plays a participant's seat from now on: an AI player standing in for it, for the reason given, or
        with None the participant again.

        The replay records the seat control line and the game's connected participants get `seat_control`, both ahead of
        the moves that follow, so a client always knows who made a move.
        """
        game = participant.game
        seat = self._seat_of(participant)
        participant.stand_in = stand_in
        if stand_in is not None:
            self._ai_replacements += 1

        if game.replay is not None:
            if stand_in is None:
                self._replay_collector.record_human_return(game.replay, seat=seat)
            else:
                self._replay_collector.record_ai_replacement(game.replay, seat=seat, reason=stand_in)

        message = SeatControlMessage(seat=seat, reason=stand_in)
        self._broadcast_to_game(game, message.payload())

    def _kick_player(self, connection: ConnectionProtocol, error: InvalidGameActionError) -> None:
        """
        Disconnect a human who sent structurally impossible input for their own seat with 1008, and seat an AI player.

        It runs the normal disconnect before the close, so the
        connection leaves the registry first and a RECONNECT pipelined
        on the closing socket is dropped. An error while replacing the
        player propagates before the close: it is a server fault, and
        the caller's boundary fails the game and closes this connection
        with 1011 itself, since the game's finalizer no longer holds it.
        """
        logger.warning("invalid game action", action=error.action, reason=error.reason)
        self.disconnect(connection)
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

        A seat that owes no action, or an action whose id is not its participant's current decision id, gets a
        `stale_action` ErrorEvent, and neither the engine nor a timer is touched. A rule judgment or race comes back
        from the engine as an ErrorEvent for the seat. Either ErrorEvent names the wait id the action echoed, so the
        client matches the refusal to its own request. Structurally impossible input (InvalidGameActionError, always the
        acting seat's) disconnects the player with 1008 and seats an AI player. Anything else the engine raises is a
        server fault and propagates to the caller's boundary, which fails the game.
        """
        participant = self._bound_participant(connection)
        if participant is None:
            return

        game = participant.game
        if game.lifecycle is GameLifecycle.PENDING:
            self._send_error(connection, code=SessionErrorCode.GAME_NOT_STARTED, message="Game has not started yet")
            return

        seat = self._seat_of(participant)
        structlog.contextvars.bind_contextvars(game_id=game.game_id, seat=seat)
        if game.awaiting is None or seat not in game.awaiting.seats or wait_id != participant.decision_id:
            self._send_stale_action(connection, seat=seat, action=action, wait_id=wait_id)
            return

        try:
            update = self._game_service.handle_action(self._runtime_of(game), seat=seat, action=action, data=data)
        except InvalidGameActionError as e:
            self._kick_player(connection, error=e)
            return

        events = [_naming_wait(event, wait_id=wait_id) for event in update.events]
        self._follow_engine(game, events=events, awaiting=update.awaiting, actor=seat)

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
            wait_id=wait_id,
        )
        connection.send_message(game_event_payload(error))

    def reconnect(self, connection: ConnectionProtocol, *, session_token: str) -> None:
        """
        Bind a new connection to a participant of a playing game and send it the game's state.

        A disconnected participant takes its seat back from the AI player (`restore_human_player`), which the replay
        records and the others get as `seat_control` (`_hand_over_seat`); a turn the AI player had not played yet, its
        delay still running, becomes the participant's own new wait, whose timer starts at once and whose scheduled AI
        turn is cancelled (`_follow_engine`). A participant still bound to a connection (a half-open socket after a
        network switch, or another client) has that connection replaced (`_bind`) instead: its seat was never handed
        over, the others never saw it leave, and the wait, its timers and the bank carry on untouched. Either way the
        new connection gets the seat's state (`_send_seat_state`). A RECONNECT on a connection the server already
        evicted is dropped unanswered.
        """
        if self._connections.get(connection.connection_id) is not connection:
            return

        participant = self._reconnecting_participant(connection, session_token=session_token)
        if participant is None:
            return

        game = participant.game
        seat = self._seat_of(participant)
        structlog.contextvars.bind_contextvars(game_id=game.game_id, seat=seat)
        runtime = self._runtime_of(game)
        taking_over = participant.is_connected
        if taking_over:
            self._bind(participant, connection)
            awaiting = self._game_service.get_awaiting(runtime)
            game.awaiting = awaiting
        else:
            awaiting = self._game_service.restore_human_player(runtime, seat)
            self._hand_over_seat(participant, stand_in=None)
            self._bind(participant, connection)
            self._follow_engine(game, events=[], awaiting=awaiting, actor=seat)
            self._reconnects += 1

        self._send_seat_state(participant, connection, awaiting=awaiting)
        logger.info("connection taken over" if taking_over else "player reconnected")

    def resync(self, connection: ConnectionProtocol) -> None:
        """
        Send the seat a bound connection holds its `game_reconnected` snapshot and the wait the game owes it again, as a
        reconnect does, on the same connection.

        Its client lost step with the server's messages; a reconnect would close the socket first and hand the seat to
        an AI player for the gap. Nothing changes hands: the connection stays bound, nobody else hears of it, and the
        wait, its timers and the bank carry on, the re-sent wait naming how long its timer has run. A connection bound
        to no participant is answered `not_in_game` (an evicted one nothing), and a pending game `game_not_started`.
        """
        participant = self._bound_participant(connection)
        if participant is None:
            return

        game = participant.game
        if game.lifecycle is GameLifecycle.PENDING:
            self._send_error(connection, code=SessionErrorCode.GAME_NOT_STARTED, message="Game has not started yet")
            return

        structlog.contextvars.bind_contextvars(game_id=game.game_id, seat=self._seat_of(participant))
        awaiting = self._game_service.get_awaiting(self._runtime_of(game))
        self._send_seat_state(participant, connection, awaiting=awaiting)
        self._resyncs += 1
        logger.info("seat resynced")

    def _send_seat_state(self, participant: Participant, connection: ConnectionProtocol, *, awaiting: Awaiting) -> None:
        """
        Send a participant's connection the `game_reconnected` snapshot of the wait `awaiting`, then the event that
        opened the wait the game owes the seat, if any, changing nothing.

        The snapshot carries the participant's latest decision id, every seat an AI player holds for its participant
        marked as such, the seat's timer settings (its bank as of its last turn) and, during a round advance (the game
        start's confirmation included), whether the seat still owes its confirmation, with how long that wait's timer
        has run and its whole timeout when it does.
        """
        game = participant.game
        seat = self._seat_of(participant)
        snapshot = self._game_service.build_reconnection_snapshot(self._runtime_of(game), seat)
        stand_ins = {self._seat_of(p): p.stand_in for p in game.participants if p.stand_in is not None}
        payload = reconnection_payload(snapshot, stand_ins=stand_ins)
        payload[WireKey.SESSION_TYPE] = SessionMessageType.GAME_RECONNECTED
        payload[WireKey.WAIT_ID] = participant.decision_id
        if awaiting.kind == WaitKind.ROUND_ADVANCE:
            payload[WireKey.CONFIRMATION_OWED] = seat in awaiting.seats
            elapsed = participant.timer.elapsed_seconds
            if seat in awaiting.seats and elapsed is not None:
                payload[WireKey.WAIT_ELAPSED] = elapsed
                payload[WireKey.ROUND_ADVANCE_SECONDS] = game.timer_config.round_advance_seconds(awaiting)

        connection.send_message(stamp_timer_settings(payload, self._timer_settings(participant)))
        self._send_wait_on_reconnect(participant, connection, awaiting=awaiting)

    def _reconnecting_participant(
        self,
        connection: ConnectionProtocol,
        *,
        session_token: str,
    ) -> Participant | None:
        """
        Return the participant a RECONNECT names, or None after answering why it cannot reconnect (yet).

        A pending game answers retry later: the client retries. A connection already bound to a participant is refused
        before any connection is replaced.
        """
        participant = self._participants_by_ticket.get(session_token)
        if participant is None:
            self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_NO_SESSION,
                message="No live game for this ticket",
            )
            return None

        if participant.game.game_id != connection.game_id:
            self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_GAME_MISMATCH,
                message="Session token is not valid for this game",
            )
            return None

        if participant.game.lifecycle is GameLifecycle.PENDING:
            self._send_error(
                connection,
                code=SessionErrorCode.RECONNECT_RETRY_LATER,
                message="Game has not started yet, retry shortly",
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

    def _send_wait_on_reconnect(
        self,
        participant: Participant,
        connection: ConnectionProtocol,
        *,
        awaiting: Awaiting,
    ) -> None:
        """Re-send the event that opened the wait the game owes a reconnected
        participant: its call prompt, or its turn's draw (the turn event after
        its own pon or chi).

        Only a taken-over seat, or a seat whose turn its AI player had not played yet, can be awaited: an AI player
        answers any call or confirmation of a seat it holds at once. The wait's timer runs from its opening (for a seat
        taken back, the reconnect itself), so nothing is re-armed. WireKey.WAIT_ELAPSED lets the client count down what
        is left and charge the bank as the server will. Sent directly instead of through `_send_events`, so the replay
        does not record the event twice.
        """
        seat = self._seat_of(participant)
        elapsed = participant.timer.elapsed_seconds
        for event in self._game_service.build_wait_events_for_seat(self._runtime_of(participant.game), seat):
            message = live_game_event_payload(event)
            if isinstance(event, CallPromptEvent):
                message = shape_call_prompt_payload(message)

            if elapsed is not None:
                message[WireKey.WAIT_ELAPSED] = elapsed

            message = stamp_wait_id(message, event=event, awaiting=awaiting, wait_id=participant.decision_id)
            connection.send_message(self._stamp_decision_bank(message, participant, awaiting))

    @staticmethod
    def _stamp_decision_bank(message: dict[int, Any], participant: Participant, awaiting: Awaiting) -> dict[int, Any]:
        """
        Stamp a turn or call opening with the bank its timer starts with (WireKey.BANK_SECONDS), so the client's
        countdown never carries an earlier decision's delivery delays into the next.
        """
        if awaiting.kind in (WaitKind.TURN, WaitKind.CALL) and WireKey.WAIT_ID in message:
            message[WireKey.BANK_SECONDS] = participant.timer.bank_seconds

        return message

    def _follow_engine(
        self,
        game: GameSession,
        *,
        events: list[GameEvent],
        awaiting: Awaiting,
        actor: int | None,
    ) -> None:
        """
        Deliver an engine call's events, drive the timers from the wait it reports, and play the AI players' turns the
        game then waits on.

        While the game waits on an AI player's turn, the AI turn delay passes in a task before the engine plays it
        (`_play_ai_turn_after_delay`), so a human sees AI turns one at a time; with no delay they are played here, one
        engine call each, until the game waits on something else.
        """
        self._apply_engine_update(game, events=events, awaiting=awaiting, actor=actor)
        while self._owes_ai_turn(game):
            if game.timer_config.ai_turn_delay_seconds > 0:
                game.ai_turn = self._spawn(self._play_ai_turn_after_delay(game))
                return

            update = self._game_service.advance_ai_turn(self._runtime_of(game))
            self._apply_engine_update(game, events=update.events, awaiting=update.awaiting, actor=None)

    @staticmethod
    def _owes_ai_turn(game: GameSession) -> bool:
        """
        Whether a playing game waits on an AI player's turn that no task is already set to play.
        """
        return (
            game.lifecycle is GameLifecycle.PLAYING
            and game.ai_turn is None
            and game.awaiting is not None
            and game.awaiting.kind == WaitKind.AI_TURN
        )

    async def _play_ai_turn_after_delay(self, game: GameSession) -> None:
        """
        Play the AI player's turn the game waits on once the AI turn delay has passed.

        After its sleep the task detaches itself from the game (`ai_turn`), so the turn it plays may schedule the next.
        Every path that ends the wait it was set for (a reconnect taking the seat back, an end claim) cancels it, even
        once its sleep ended, so it only ever plays the AI turn it was set for. It logs as its game alone, never as the
        seat whose move scheduled it. Any unexpected error ends the game through fail_game.
        """
        await asyncio.sleep(game.timer_config.ai_turn_delay_seconds)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(game_id=game.game_id)
        game.ai_turn = None
        try:
            update = self._game_service.advance_ai_turn(self._runtime_of(game))
            self._follow_engine(game, events=update.events, awaiting=update.awaiting, actor=None)
        except Exception as exc:  # noqa: BLE001
            self.fail_game(game, reason="AI turn failed", exc=exc)

    def _apply_engine_update(
        self,
        game: GameSession,
        *,
        events: list[GameEvent],
        awaiting: Awaiting,
        actor: int | None,
    ) -> None:
        """
        Deliver an engine call's events and drive the timers from the wait it reports.

        The call's actor is the seat that acted, timed out, was replaced or took its seat back; a game start or an AI
        player's turn has none. When the wait id changed, every timer stops (charging elapsed decision time) and so does
        a pending AI turn, a new round's banks reset, and each connected participant now awaited advances its own
        decision id before the events go out. The new wait's timers start after them; an AI player's turn awaits no
        participant and starts none. When it did not, only an actor that left the wait (a partial prompt response or
        confirmation) has its timer stopped; an actor still awaited (an error) keeps it running with nothing deducted.
        """
        previous = game.awaiting
        game.awaiting = awaiting
        new_wait = previous is None or awaiting.wait_id != previous.wait_id
        if new_wait:
            self._end_wait_timers(game)
            self._cancel_ai_turn(game)
            self._reset_round_banks(game, previous=previous, awaiting=awaiting)
            for participant in game.connected():
                if participant.seat in awaiting.seats:
                    participant.decision_id += 1
        elif actor is not None and actor in previous.seats and actor not in awaiting.seats:
            self._stop_timer_at(game, actor)

        self._broadcast_events(game, events, awaiting)
        if new_wait and game.lifecycle is GameLifecycle.PLAYING:
            self._start_wait_timers(game, awaiting=awaiting)

    @staticmethod
    def _end_wait_timers(game: GameSession) -> None:
        """
        Charge every running decision when its wait ends, including calls resolved by another seat.
        """
        for participant in game.participants:
            participant.timer.stop()

    @staticmethod
    def _cancel_ai_turn(game: GameSession) -> None:
        if game.ai_turn is not None:
            game.ai_turn.cancel()
            game.ai_turn = None

    @staticmethod
    def _stop_timer_at(game: GameSession, seat: int) -> None:
        participant = game.at_seat(seat)
        if participant is not None:
            participant.timer.stop()

    @staticmethod
    def _reset_round_banks(game: GameSession, *, previous: Awaiting | None, awaiting: Awaiting) -> None:
        """
        Reset every participant's bank on the first wait of each round, including absent seats and the first round,
        before sending the opening messages.
        """
        if previous is None or awaiting.round_number != previous.round_number:
            for participant in game.participants:
                participant.timer.reset_bank()

    def _start_wait_timers(self, game: GameSession, *, awaiting: Awaiting) -> None:
        """
        Start the timers of a new wait for its awaited seats that have a connected participant.
        """
        connected = sorted(game.connected(), key=self._seat_of)
        if awaiting.kind == WaitKind.ROUND_ADVANCE:
            for participant in connected:
                self._start_round_advance_timer(participant, awaiting=awaiting)

            return

        for participant in connected:
            if participant.seat not in awaiting.seats:
                continue

            if awaiting.kind == WaitKind.TURN:
                self._start_turn_timer(participant)
            else:
                self._start_meld_timer(participant)

    def _start_turn_timer(self, participant: Participant) -> None:
        participant.timer.start_decision_timer(lambda: self._handle_timeout(participant, TimeoutType.TURN))

    def _start_meld_timer(self, participant: Participant) -> None:
        participant.timer.start_decision_timer(lambda: self._handle_timeout(participant, TimeoutType.MELD))

    def _start_round_advance_timer(self, participant: Participant, *, awaiting: Awaiting) -> None:
        """
        Start the round advance timer: the round advance timeout once for each result the round end shows in turn, or
        the game start confirmation's timeout.
        """
        participant.timer.start_fixed_timer(
            participant.game.timer_config.round_advance_seconds(awaiting),
            lambda: self._handle_timeout(participant, TimeoutType.ROUND_ADVANCE),
        )

    def _broadcast_events(self, game: GameSession, events: list[GameEvent], awaiting: Awaiting) -> None:
        """
        Send an engine call's events; after a batch with which the game waits for nothing, claim its completion.

        Nothing between the sends and the claim can suspend, and the game end is queued to every socket before the
        finalizer queues its close. If a send raises (an encoding error), nothing was claimed and the caller's boundary
        fails the game.
        """
        self._send_events(game, events, awaiting)
        if awaiting.kind == WaitKind.NONE:
            game_ended_event = next((e for e in events if isinstance(e, GameEndedEvent)), None)
            self._end_game(game, GameEndReason.COMPLETED, game_ended_event=game_ended_event)

    def _send_events(self, game: GameSession, events: list[GameEvent], awaiting: Awaiting) -> None:
        """
        Record the events for the replay, then send each to its target, the wait's opening messages stamped with
        WireKey.WAIT_ID.

        Each game start copy carries its recipient's WireKey.SEAT. A draw goes whole to the drawer and as its public
        notice to every other seat, so each seat gets one representation of it. The round end that opens a round
        advance, and the deal that opens the game start's confirmation, also name its whole timeout
        (WireKey.ROUND_ADVANCE_SECONDS), so the client counts it down by the server's word rather than by its own count
        of the results.
        """
        if game.replay is not None:
            self._replay_collector.collect_events(game.replay, events)

        for event in events:
            message = live_game_event_payload(event)
            if isinstance(event, CallPromptEvent):
                message = shape_call_prompt_payload(message)

            if isinstance(event, GameStartedEvent):
                self._send_to_each_seat(game, message)
            elif isinstance(event.target, BroadcastTarget):
                for participant in game.connected():
                    self._send_event_to_participant(participant, message=message, event=event, awaiting=awaiting)
            elif isinstance(event.target, SeatTarget):
                participant = game.at_seat(event.target.seat)
                if participant is not None:
                    self._send_event_to_participant(participant, message=message, event=event, awaiting=awaiting)

                if isinstance(event, DrawEvent):
                    self._send_draw_notice(game, event)

    def _send_event_to_participant(
        self,
        participant: Participant,
        *,
        message: dict[int, Any],
        event: GameEvent,
        awaiting: Awaiting,
    ) -> None:
        if participant.connection is None:
            return

        payload = stamp_wait_id(message, event=event, awaiting=awaiting, wait_id=participant.decision_id)
        if awaiting.kind == WaitKind.ROUND_ADVANCE and WireKey.WAIT_ID in payload:
            payload[WireKey.ROUND_ADVANCE_SECONDS] = participant.game.timer_config.round_advance_seconds(awaiting)

        participant.connection.send_message(
            self._stamp_decision_bank(payload, participant=participant, awaiting=awaiting)
        )

    @staticmethod
    def _send_draw_notice(game: GameSession, event: DrawEvent) -> None:
        """
        Send a draw's public notice to every connected participant but the drawer's, whose seat gets the draw itself.
        """
        notice = draw_notice_payload(event)
        for participant in game.participants:
            if participant.connection is not None and participant.seat != event.seat:
                participant.connection.send_message(notice)

    def _send_to_each_seat(self, game: GameSession, message: dict[int, Any]) -> None:
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
            max_bank_seconds=config.initial_bank_seconds,
            round_advance_timeout_seconds=config.round_advance_timeout_seconds,
            game_start_confirm_seconds=config.game_start_confirm_seconds,
        )

    @staticmethod
    def _broadcast_to_game(
        game: GameSession,
        message: dict[int, Any],
    ) -> None:
        """
        Send a message to every connected participant of the game.
        """
        for participant in game.participants:
            if participant.connection is not None:
                participant.connection.send_message(message)

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
        cancel after its sleep ended still stops it before this runs. It logs as the timer's own seat: the timer task
        copied the log context of whatever armed it, often another seat's action.
        """
        game = participant.game
        structlog.contextvars.bind_contextvars(game_id=game.game_id, seat=participant.seat)
        try:
            seat = self._seat_of(participant)
            update = self._game_service.handle_timeout(self._runtime_of(game), seat=seat, timeout_type=timeout_type)
            self._timeouts[timeout_type] += 1
            self._follow_engine(game, events=update.events, awaiting=update.awaiting, actor=seat)
        except Exception as exc:  # noqa: BLE001
            self.fail_game(game, reason=f"{timeout_type} timeout failed", exc=exc)

    def _end_game(
        self,
        game: GameSession,
        reason: GameEndReason,
        *,
        game_ended_event: GameEndedEvent | None = None,
    ) -> None:
        """
        Claim a game's end and release it, synchronously, then hand its effects to one owned finalizer.

        Only a pending or playing game can be claimed; a later call does nothing. The claim first detaches the connected
        participants' connections and the replay lines (an abandoned game's replay is discarded) and spawns the
        finalizer on them, so a release step that raised would still leave the game finished. It then drops the game and
        its tickets from the registry, cancels the pending timeout, the AI turn and every sleeping timer, evicts the
        detached connections and drops the engine runtime. The finalizer saves the replay, posts the finish record and
        closes the detached connections (1000 for a completion, `internal_error` and 1011 for a failure).
        """
        if not game.is_active:
            return

        game.lifecycle = GameLifecycle.ENDING
        connections = [participant.connection for participant in game.participants if participant.connection]
        replay_records = game.replay.records if game.replay is not None and reason != GameEndReason.ABANDONED else None
        game.replay = None
        self._spawn(
            self._finish_game(
                game,
                _Ending(
                    reason=reason,
                    connections=connections,
                    replay_records=replay_records,
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

        for task in (game.pending_timeout, game.ai_turn):
            if task is not None:
                task.cancel()

        game.pending_timeout = None
        game.ai_turn = None
        for connection in connections:
            self._evict_connection(connection)

        game.runtime = None

    async def _finish_game(self, game: GameSession, ending: _Ending) -> None:
        """
        Run the effects of a game's end on what the claim detached: replay, finish record, closes.

        Each step is its own error boundary: an unexpected failure is logged and the steps after it, down to the last
        close, still run. Any error saving a completed game's replay, storage errors included, turns its end into a
        failure. A game with no start record (it never started) records no finish. It logs as its game alone, never as
        the seat whose action or timeout claimed the end.
        """
        game_id = game.game_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(game_id=game_id)
        end_reason = ending.reason
        if ending.replay_records is not None:
            try:
                await self._replay_collector.save(game_id, ending.replay_records)
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

    def fail_game(self, game: GameSession, *, reason: str, exc: BaseException | None = None) -> None:
        """
        End a game on a server fault: the one terminal path for one, idempotent and callable from any context.

        It claims the game's end as ERROR (`_end_game`) synchronously, so a later action, timeout, join or reconnect
        finds no game. The finalizer records the error end, saves whatever replay history exists, and sends every
        connected participant an `internal_error` session error before closing with 1011. The current task is never
        cancelled or awaited. A game whose end was already claimed keeps that end. Either way the caller skips its
        normal broadcast and timers.
        """
        logger.error("game failed", game_id=game.game_id, reason=reason, exc_info=exc)
        self._end_game(game, GameEndReason.ERROR)

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

        With a game (the one the connection was acting in, captured
        before the failing call), the game ends through fail_game, whose
        finalizer closes its connected participants; the connection
        itself is evicted from the registry and closed with 1011 here
        when it is not among them (a join or reconnect that failed
        before binding it, a participant already gone). With no game
        there is nothing to fail: the fault is logged with its
        traceback, and the connection evicted and closed with 1011. The
        eviction comes first, so a JOIN_GAME or RECONNECT pipelined
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
                connection.send_message(message.payload())
            finally:
                connection.close(code=1011, reason="internal_error")
        except Exception:
            logger.exception("failed to close a connection of a failed game", connection_id=connection.connection_id)

    async def shutdown(self) -> None:
        """
        Stop every background task before the server's resources close; it ends no game itself.

        A graceful stop ends games only through the normal leave of each closed socket, which on the normal path runs
        before this (`docs/architecture.md`). The sleeping tasks still registered are cancelled in one step, so none can
        fire and start or end a game meanwhile. Every other task the manager spawned, each game's finalizer among them,
        is awaited, never cancelled, so its replay save, finish record post and socket closes complete. A game still
        registered vanishes with no record.
        """
        sleeping = [
            task for game in self._games.values() for task in (game.pending_timeout, game.ai_turn) if task is not None
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

        The task detaches itself from `_auth_timeouts` after its sleep,
        so cancel paths leave the close alone. Binding or evicting the
        connection cancels it, even once its sleep ended, so it only
        ever closes a registered connection that never authenticated. An
        unexpected error is logged and the connection closed with 1011:
        there is no game to fail yet.
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
