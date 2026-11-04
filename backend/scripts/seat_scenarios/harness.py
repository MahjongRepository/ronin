from __future__ import annotations

import asyncio
import dataclasses
import functools
import json
import selectors
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, NoReturn, override

from game.logic.events import DrawEvent, RoundStartedEvent
from game.logic.game import init_round
from game.logic.mahjong_service import MahjongGameService
from game.logic.settings import GameSettings
from game.messaging.encoder import decode, encode
from game.messaging.protocol import ConnectionProtocol
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.session.manager import SessionManager
from game.session.models import PlayerSpec
from game.session.replay_collector import ReplayCollector
from game.tests.helpers.auth import TEST_TICKET_SECRET, make_test_game_ticket
from game.tests.mocks import FakeGameRepository, FakeReplayStorage
from game.wire.enums import WireEventType
from game.wire.keys import WireKey
from scripts.replay_fixtures.staged_game import STAGED_SEED, ScenarioError

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence
    from concurrent.futures import Executor
    from contextvars import Context

    from game.logic.enums import GameAction, KanType, TimeoutType
    from game.logic.events import GameEvent
    from game.logic.runtime import GameRuntime
    from game.logic.service import GameStart, GameUpdate
    from game.logic.state import MahjongGameState
    from scripts.replay_fixtures.staged_game import StagedWall

TIME_GRAIN_SECONDS = 0.25
UNSEEN_DROP_CODE = 1006
GAME_TICKET_PLACEHOLDER = "<game ticket>"


class VirtualTimeLoop(asyncio.SelectorEventLoop):
    """
    An event loop on virtual time: whenever it would wait, for a timer or for I/O, it jumps its clock to the moment the
    wait ends instead, so sleeps take no real time and every timer fires at its exact virtual moment.

    It keeps the timers it was asked for, so a scripted step can refuse to fall on the moment one fires, and it runs no
    thread: the one executor call it allows, a finished game's replay save into the in-memory storage, runs inline at
    once, and any other raises, so a blocking call new on the server's path cannot slip past the scenarios unseen.
    """

    def __init__(self) -> None:
        self._now = 0.0
        self._timers: list[asyncio.TimerHandle] = []
        super().__init__(selector=_AdvancingSelector(self))

    @override
    def time(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    @override
    def call_at(  # deadcode: ignore
        self,
        when: float,
        callback: Callable[..., object],
        *args: Any,
        context: Context | None = None,
    ) -> asyncio.TimerHandle:
        handle = super().call_at(when, callback, *args, context=context)
        self._timers.append(handle)
        return handle

    def has_timer_at(self, when: float) -> bool:
        """
        Whether a timer still armed falls due exactly at `when`, a moment ahead of the clock.
        """
        self._timers = [timer for timer in self._timers if not timer.cancelled() and timer.when() >= self._now]
        return when > self._now and any(timer.when() == when for timer in self._timers)

    @override
    def run_in_executor(  # deadcode: ignore
        self, executor: Executor | None, func: Callable[..., Any], *args: Any
    ) -> asyncio.Future[Any]:
        if not _is_replay_save(func):
            raise ScenarioError(
                "the harness runs no thread, but a call other than the replay save asked for an executor"
            )
        future: asyncio.Future[Any] = self.create_future()
        future.set_result(func(*args))
        return future


def _is_replay_save(func: Callable[..., Any]) -> bool:
    """
    Whether an executor call is `asyncio.to_thread`'s wrapper (a partial of a context's `run`) around the in-memory
    replay storage's save.
    """
    if not isinstance(func, functools.partial) or not func.args:
        return False
    target = func.args[0]
    return isinstance(getattr(target, "__self__", None), FakeReplayStorage) and target.__name__ == "save_replay"


class _AdvancingSelector(selectors.SelectSelector):
    """
    A selector that never blocks: asked to wait up to a timeout, it moves its loop's clock on by the timeout and reports
    no I/O, since the harness's sockets are in memory.
    """

    def __init__(self, loop: VirtualTimeLoop) -> None:
        super().__init__()
        self._loop = loop

    @override
    def select(  # deadcode: ignore
        self, timeout: float | None = None
    ) -> list[tuple[selectors.SelectorKey, int]]:
        if timeout is None:
            raise ScenarioError("the loop would wait forever: no step is pending and no timer is armed")

        self._loop.advance(timeout)
        return []


class _StagedEngine(MahjongGameService):
    """
    The real engine, dealing every game it starts from the staged seed and wall, as the session starts one with neither.

    The rounds after the first are dealt from the staged later rounds' walls in order, each checked against the dealer
    the game advanced to, and from the seed once those run out. Each staged draw of a round is checked against the seat
    that draws it, in order. A check that fails inside the session, which answers the client with a server error, is
    kept as the engine's failure for the scenario to raise with its cause.
    """

    def __init__(self, staged: StagedWall, settings: GameSettings, later_rounds: Sequence[StagedWall]) -> None:
        super().__init__()
        if staged.dealer != 0:
            raise ScenarioError(f"a staged game's first round is dealt from seat 0, not {staged.dealer}")

        self._wall = staged.tiles()
        self._settings = settings
        self._later_rounds = tuple(later_rounds)
        self._later_rounds_dealt = 0
        self._rounds_to_deal: list[Sequence[tuple[int, int]]] = [staged.draws, *(r.draws for r in later_rounds)]
        self._round_draws: Sequence[tuple[int, int]] = ()
        self._next_draw = 0
        self.failure: ScenarioError | None = None

    def require_later_rounds_dealt(self, game_id: str) -> None:
        if self._later_rounds_dealt != len(self._later_rounds):
            raise ScenarioError(
                f"{game_id}: {len(self._later_rounds)} later rounds were staged, {self._later_rounds_dealt} dealt"
            )

    @override
    def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
    ) -> GameStart:
        if seed is not None or settings is not None or wall is not None:
            raise ScenarioError(f"{game_id}: the session started a game with its own seed, settings or wall")

        start = super().start_game(
            game_id, player_names, seed=STAGED_SEED, settings=self._settings, wall=list(self._wall)
        )
        self._check_draws(start.events)
        return start

    @override
    def handle_action(self, runtime: GameRuntime, *, seat: int, action: GameAction, data: dict[str, Any]) -> GameUpdate:
        update = super().handle_action(runtime, seat=seat, action=action, data=data)
        self._check_draws(update.events)
        return update

    @override
    def handle_timeout(self, runtime: GameRuntime, *, seat: int, timeout_type: TimeoutType) -> GameUpdate:
        update = super().handle_timeout(runtime, seat=seat, timeout_type=timeout_type)
        self._check_draws(update.events)
        return update

    @override
    def process_ai_player_actions_after_replacement(self, runtime: GameRuntime, seat: int) -> GameUpdate:
        update = super().process_ai_player_actions_after_replacement(runtime, seat)
        self._check_draws(update.events)
        return update

    @override
    def _deal_next_round(self, game_state: MahjongGameState) -> MahjongGameState:
        if self._later_rounds_dealt == len(self._later_rounds):
            return super()._deal_next_round(game_state)

        staged = self._later_rounds[self._later_rounds_dealt]
        dealer = game_state.round_state.dealer_seat
        if staged.dealer != dealer:
            self._fail(f"later round {self._later_rounds_dealt} was staged for dealer {staged.dealer}, not {dealer}")

        self._later_rounds_dealt += 1
        return init_round(game_state, wall=list(staged.tiles()))

    def _check_draws(self, events: Sequence[GameEvent]) -> None:
        """
        Check each draw of a staged tile in the events against the seat and the order the round staged it in.

        A deal (its run of round starts) begins the next staged round's draws, or none once a round is dealt from the
        seed, whose tile ids say nothing of the staged walls.
        """
        dealing = False
        for event in events:
            if isinstance(event, RoundStartedEvent):
                if not dealing:
                    self._round_draws = self._rounds_to_deal.pop(0) if self._rounds_to_deal else ()
                    self._next_draw = 0

                dealing = True
                continue

            dealing = False
            if isinstance(event, DrawEvent):
                self._check_draw(event)

    def _check_draw(self, draw: DrawEvent) -> None:
        staged = [index for index, (_, tile_id) in enumerate(self._round_draws) if tile_id == draw.tile_id]
        if not staged:
            return

        (index,) = staged
        seat = self._round_draws[index][0]
        if index != self._next_draw or draw.seat != seat:
            self._fail(f"seat {draw.seat} drew staged draw {index} (staged for seat {seat}) as draw {self._next_draw}")

        self._next_draw += 1

    def _fail(self, message: str) -> NoReturn:
        self.failure = ScenarioError(message)
        raise self.failure


class _ClientSocket(ConnectionProtocol):
    """
    One socket of a seat's client, in memory: what the server sends it and its close go to the client, decoded.

    A close the server queues ends the socket as the endpoint's would: the router's disconnect runs once, on the loop's
    next turn, as the endpoint's receive loop ends.
    """

    def __init__(self, client: SeatClient, connection_id: str) -> None:
        self._client = client
        self._connection_id = connection_id
        self._closed = False

    @property
    @override
    def connection_id(self) -> str:
        return self._connection_id

    @property
    @override
    def game_id(self) -> str:
        return self._client.game_id

    @override
    def send_bytes(self, data: bytes) -> None:
        if not self._closed:
            self._client.receive(self, decode(data))

    @override
    async def receive_bytes(self) -> bytes:
        raise ConnectionError("the harness hands client messages to the router itself")

    @override
    def close(self, code: int = 1000, reason: str = "") -> None:
        if self._closed:
            return

        self._closed = True
        self._client.lose(self, code=code, reason=reason)
        asyncio.get_running_loop().call_soon(self._client.router.handle_disconnect, self)


class EventKind(StrEnum):
    OPENED = "opened"
    RECEIVED = "received"
    SENT = "sent"
    CLOSED = "closed"


@dataclass(frozen=True)
class TranscriptEvent:
    """
    One event of a seat's transcript at its logical time in milliseconds: its kind's fields (a received payload, a sent
    message, a close's code and reason) and the label a scenario named it by.
    """

    at: int
    kind: EventKind
    fields: Mapping[str, Any]
    label: str | None = None

    def as_json(self) -> dict[str, Any]:
        label = {} if self.label is None else {"label": self.label}
        return {"at": self.at, "kind": self.kind.value, **self.fields, **label}


def _is_refusal(payload: Mapping[int, Any]) -> bool:
    return (
        payload.get(WireKey.EVENT_TYPE) == WireEventType.ERROR
        or payload.get(WireKey.SESSION_TYPE) == SessionMessageType.ERROR
    )


def _matches(payload: Mapping[int, Any], kind: WireEventType | SessionMessageType) -> bool:
    if isinstance(kind, SessionMessageType):
        return payload.get(WireKey.SESSION_TYPE) == kind

    return payload.get(WireKey.EVENT_TYPE) == kind and WireKey.SESSION_TYPE not in payload


def _as_wire(message: Mapping[int, Any]) -> dict[int, Any]:
    """
    Return a client message as the router gets it from a socket: through MessagePack, plain integers and strings.
    """
    return decode(encode(dict(message)))


class SeatClient:
    """
    One player's game client as the server meets it: it opens sockets, identifies, and answers the waits it is sent,
    each at a scripted virtual time, echoing the wait id it last received as a client does.

    Its transcript is what the client met, in order, with the logical time in milliseconds: each socket it opened, each
    message its current socket received (decoded exactly as sent), each message it sent (its JOIN_GAME or RECONNECT with
    the ticket replaced by GAME_TICKET_PLACEHOLDER), and each close it saw. A socket the client lost is dead to it: the
    server may still send to it or close it, unseen.
    """

    def __init__(self, game: SeatedGame, *, name: str, ticket: str) -> None:
        self.name = name
        self.ticket = ticket
        self.seat: int | None = None
        self._game = game
        self._events: list[TranscriptEvent] = []
        self._socket: _ClientSocket | None = None
        self._sockets_opened = 0
        self._wait_id: int | None = None
        self._refusals: list[Mapping[int, Any]] = []
        self._expected_refusals: list[SessionErrorCode] = []

    @property
    def game_id(self) -> str:
        return self._game.game_id

    @property
    def router(self) -> MessageRouter:
        return self._game.router

    @property
    def events(self) -> tuple[TranscriptEvent, ...]:
        return tuple(self._events)

    def refusals(self) -> list[Mapping[int, Any]]:
        return list(self._refusals)

    def expected_refusals(self) -> list[SessionErrorCode]:
        return list(self._expected_refusals)

    def receive(self, socket: _ClientSocket, payload: dict[int, Any]) -> None:
        if socket is not self._socket:
            return

        self._record(EventKind.RECEIVED, {"payload": payload})
        if _is_refusal(payload):
            self._take_refusal(payload)

        if WireKey.WAIT_ID in payload:
            self._wait_id = payload[WireKey.WAIT_ID]

        if (
            payload.get(WireKey.EVENT_TYPE) == WireEventType.GAME_STARTED
            or payload.get(WireKey.SESSION_TYPE) == SessionMessageType.GAME_RECONNECTED
        ):
            self.seat = payload[WireKey.SEAT]

    def lose(self, socket: _ClientSocket, *, code: int, reason: str) -> None:
        if socket is not self._socket:
            return

        self._socket = None
        self._record(EventKind.CLOSED, {"code": code, "reason": reason})

    def join(self, *, at: float, label: str | None = None) -> None:
        self._game.run_at(at, lambda: self._open(WireClientMessageType.JOIN_GAME, label=label))

    def reconnect(self, *, at: float, label: str | None = None) -> None:
        """
        Open a new socket and RECONNECT on it, after a drop the server may or may not have seen.
        """
        self._game.run_at(at, lambda: self._open(WireClientMessageType.RECONNECT, label=label))

    def drop_unseen(self, *, at: float, label: str | None = None) -> None:
        """
        Lose the socket as a half-open connection does: the client sees it close with the code a browser reports for a
        socket that died without a close frame, while the server sees nothing and keeps the seat bound to it.
        """
        self._drop(at=at, label=label, server_sees=False)

    def drop_seen(self, *, at: float, label: str | None = None) -> None:
        """
        Lose the socket as a dropped connection the server notices does: the client sees it close as `drop_unseen` does,
        and the server takes the participant out of its game, an AI player taking the seat while it plays.
        """
        self._drop(at=at, label=label, server_sees=True)

    def be_replaced_by_another_tab(self, *, at: float, label: str | None = None) -> None:
        """
        Let another client of the same player, unrecorded, RECONNECT and take the seat over from this one's socket,
        whose close the label names.
        """

        def replace() -> None:
            self._sockets_opened += 1
            rival = _ClientSocket(self, f"{self.name}-rival-{self._sockets_opened}")
            self.router.handle_connect(rival)
            self.router.handle_message(rival, _as_wire(self._identity(WireClientMessageType.RECONNECT)))
            if self._socket is not None:
                raise ScenarioError(f"{self.name}: another tab reconnected, and this one's socket stayed open")

            self._label_last(label)

        self._game.run_at(at, replace)

    def discard(self, tile_id: int, *, at: float, label: str | None = None) -> None:
        self._act(WireGameAction.DISCARD, {WireKey.TILE_ID: tile_id}, at=at, label=label)

    def riichi(self, tile_id: int, *, at: float, label: str | None = None) -> None:
        self._act(WireGameAction.DECLARE_RIICHI, {WireKey.TILE_ID: tile_id}, at=at, label=label)

    def tsumo(self, *, at: float, label: str | None = None) -> None:
        self._act(WireGameAction.DECLARE_TSUMO, {}, at=at, label=label)

    def ron(self, *, at: float, label: str | None = None) -> None:
        self._act(WireGameAction.CALL_RON, {}, at=at, label=label)

    def pon(self, tile_id: int, *, at: float, label: str | None = None) -> None:
        self._act(WireGameAction.CALL_PON, {WireKey.TILE_ID: tile_id}, at=at, label=label)

    def chi(self, tile_id: int, sequence: tuple[int, int], *, at: float, label: str | None = None) -> None:
        self._act(
            WireGameAction.CALL_CHI,
            {WireKey.TILE_ID: tile_id, WireKey.SEQUENCE_TILES: list(sequence)},
            at=at,
            label=label,
        )

    def kan(self, tile_id: int, kan_type: KanType, *, at: float, label: str | None = None) -> None:
        self._act(
            WireGameAction.CALL_KAN,
            {WireKey.TILE_ID: tile_id, WireKey.ACTION_KAN_TYPE: kan_type.value},
            at=at,
            label=label,
        )

    def kyuushu(self, *, at: float, label: str | None = None) -> None:
        self._act(WireGameAction.CALL_KYUUSHU, {}, at=at, label=label)

    def pass_(self, *, at: float, label: str | None = None) -> None:
        self._act(WireGameAction.PASS, {}, at=at, label=label)

    def confirm_round(self, *, at: float, label: str | None = None) -> None:
        self._act(WireGameAction.CONFIRM_ROUND, {}, at=at, label=label)

    def resync(self, *, at: float, label: str | None = None, refused_with: SessionErrorCode | None = None) -> None:
        """
        Ask for the seat's state again on the open socket, as a client that lost step with the server's messages does.

        `refused_with` names the session error the server must answer it with, which then fails nothing.
        """

        def send() -> None:
            socket = self._require_socket()
            message = _as_wire({WireKey.EVENT_TYPE: WireClientMessageType.RESYNC})
            self._record(EventKind.SENT, {"message": message})
            self._label_last(label)
            if refused_with is not None:
                self._expected_refusals.append(refused_with)

            self.router.handle_message(socket, message)

        self._game.run_at(at, send)

    def label(self, name: str, kind: WireEventType | SessionMessageType) -> None:
        """
        Name the last message of the kind the client received, which must carry no name yet.
        """
        for index in range(len(self._events) - 1, -1, -1):
            event = self._events[index]
            if event.kind != EventKind.RECEIVED or not _matches(event.fields["payload"], kind):
                continue

            if event.label is not None:
                raise ScenarioError(f"{self.name}: the last {kind!r} is already labelled {event.label}")

            self._events[index] = dataclasses.replace(event, label=name)
            return

        raise ScenarioError(f"{self.name}: received no {kind!r} to label {name}")

    def _take_refusal(self, payload: Mapping[int, Any]) -> None:
        """
        Take a refusal as the one the scenario expects next, or keep it as one that fails the scenario.
        """
        if self._expected_refusals and payload.get(WireKey.SESSION_ERROR_CODE) == self._expected_refusals[0]:
            self._expected_refusals.pop(0)
            return

        self._refusals.append(payload)

    def _identity(self, message_type: WireClientMessageType) -> dict[int, Any]:
        return {WireKey.EVENT_TYPE: message_type, WireKey.GAME_TICKET: self.ticket}

    def _open(self, identity: WireClientMessageType, *, label: str | None) -> None:
        if self._socket is not None:
            raise ScenarioError(f"{self.name}: opened a socket while one is open")

        self._sockets_opened += 1
        self._socket = _ClientSocket(self, f"{self.name}-{self._sockets_opened}")
        self._record(EventKind.OPENED, {})
        self._label_last(label)
        self.router.handle_connect(self._socket)

        message = _as_wire(self._identity(identity))
        self._record(EventKind.SENT, {"message": {**message, WireKey.GAME_TICKET: GAME_TICKET_PLACEHOLDER}})
        self.router.handle_message(self._socket, message)

    def _drop(self, *, at: float, label: str | None, server_sees: bool) -> None:
        def drop() -> None:
            socket = self._require_socket()
            self.lose(socket, code=UNSEEN_DROP_CODE, reason="")
            self._label_last(label)
            if server_sees:
                self.router.handle_disconnect(socket)

        self._game.run_at(at, drop)

    def _act(self, action: WireGameAction, fields: dict[int, object], *, at: float, label: str | None) -> None:
        def send() -> None:
            socket = self._require_socket()
            if self._wait_id is None:
                raise ScenarioError(f"{self.name}: {action.name} before any wait was opened")

            message = _as_wire(
                {
                    WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
                    WireKey.ACTION: action,
                    **fields,
                    WireKey.WAIT_ID: self._wait_id,
                }
            )
            self._record(EventKind.SENT, {"message": message})
            self._label_last(label)
            self.router.handle_message(socket, message)

        self._game.run_at(at, send)

    def _require_socket(self) -> _ClientSocket:
        if self._socket is None:
            raise ScenarioError(f"{self.name}: acted without an open socket")

        return self._socket

    def _record(self, kind: EventKind, fields: Mapping[str, Any]) -> None:
        self._events.append(TranscriptEvent(at=self._game.now_ms(), kind=kind, fields=fields))

    def _label_last(self, label: str | None) -> None:
        if label is not None:
            self._events[-1] = dataclasses.replace(self._events[-1], label=label)


@dataclass(frozen=True)
class SeatTranscript:
    """
    What one seat's client met in a scenario (`SeatClient`), as the committed fixture holds it.
    """

    scenario: str
    game_id: str
    seat: int
    events: tuple[TranscriptEvent, ...]

    @property
    def file_name(self) -> str:
        return f"{self.scenario}_seat_{self.seat}.json"

    @property
    def text(self) -> str:
        """
        The transcript as JSON with one event per line, every object's keys sorted.
        """
        header = {"game_id": self.game_id, "scenario": self.scenario, "seat": self.seat}
        fields = [f"  {json.dumps(key)}: {json.dumps(value, allow_nan=False)}," for key, value in header.items()]
        events = ",\n".join(
            f"    {json.dumps(event.as_json(), sort_keys=True, allow_nan=False)}" for event in self.events
        )
        return "\n".join(["{", *fields, '  "events": [', events, "  ]", "}"]) + "\n"


class SeatedGame:
    """
    A game the real session manager runs, from its pending registration on, for scripted human clients over in-memory
    sockets, on virtual time; the engine deals it from a staged wall, and its next rounds from the later rounds' walls
    when any are staged, and seats AI players in the seats no player takes.

    Client messages go through the real message router, and the session's own pacing runs as in production: the default
    timer settings, the game start pause before the deal, the turn, call and round advance timers with their banks, all
    timed by the loop's virtual clock. A refusal any client receives (a game error or a session error) that its step did
    not expect fails the scenario at once. Open one with `seated_game`, which stops it and closes its loop.
    """

    def __init__(self, loop: VirtualTimeLoop, game_id: str, engine: _StagedEngine, *, players: Sequence[str]) -> None:
        self.game_id = game_id
        self._loop = loop
        self._engine = engine
        self._manager = SessionManager(
            self._engine,
            game_repository=FakeGameRepository(),
            replay_collector=ReplayCollector(FakeReplayStorage()),
            clock=loop.time,
        )
        self.router = MessageRouter(self._manager, game_ticket_secret=TEST_TICKET_SECRET)

        self.clients = {
            name: SeatClient(self, name=name, ticket=make_test_game_ticket(username=name, room_id=game_id))
            for name in players
        }
        specs = [
            PlayerSpec(name=name, user_id=f"user-{name}", game_ticket=client.ticket)
            for name, client in self.clients.items()
        ]
        self.run_at(0, lambda: self._manager.create_pending_game(game_id=game_id, player_specs=specs))

    def now_ms(self) -> int:
        return round(self._loop.time() * 1000)

    def run_at(self, at: float, step: Callable[[], None]) -> None:
        """
        Run the game on virtual time up to `at` seconds, every server timer due by then firing at its moment, then take
        the step; raise ScenarioError when any client was refused meanwhile.

        `at` is a multiple of TIME_GRAIN_SECONDS, so with the whole-second pacing of the timer settings every time, bank
        and elapsed time the server computes is exact in binary and prints the same on every run. It never falls on the
        moment a server timer fires, which would leave their order to the loop's scheduling.
        """
        if at < self._loop.time():
            raise ScenarioError(f"{self.game_id}: a step at {at}s after the clock reached {self._loop.time()}s")

        if (at / TIME_GRAIN_SECONDS) % 1:
            raise ScenarioError(f"{self.game_id}: a step at {at}s, not a multiple of {TIME_GRAIN_SECONDS}s")

        if self._loop.has_timer_at(at):
            raise ScenarioError(f"{self.game_id}: a step at {at}s, the moment a server timer fires")

        self._loop.run_until_complete(self._step_at(at, step))
        self._require_no_refusal()

    def wait_until(self, at: float) -> None:
        """
        Run the game on virtual time up to `at` seconds with no client step, so its timers' messages arrive first.
        """
        self.run_at(at, lambda: None)

    def transcripts(self, scenario: str, *names: str) -> tuple[SeatTranscript, ...]:
        """
        Return the named clients' transcripts, once every staged later round was dealt.
        """
        self._require_no_refusal()
        self._engine.require_later_rounds_dealt(self.game_id)

        transcripts = []
        for name in names:
            client = self.clients[name]
            if client.seat is None:
                raise ScenarioError(f"{self.game_id}: {name} never learned its seat")

            transcripts.append(
                SeatTranscript(scenario=scenario, game_id=self.game_id, seat=client.seat, events=client.events)
            )

        return tuple(transcripts)

    def stop(self) -> None:
        """
        Stop every timer and wait for every task the session manager owns.
        """
        self._loop.run_until_complete(self._manager.shutdown())

    async def _step_at(self, at: float, step: Callable[[], None]) -> None:
        await asyncio.sleep(at - self._loop.time())
        step()

    def _require_no_refusal(self) -> None:
        """
        Raise ScenarioError for the engine's failed check, the cause of the server error a client got for it, else for
        any client's refusal, or a refusal it expected that never came.
        """
        failure = self._engine.failure
        if failure is not None:
            raise ScenarioError(f"{self.game_id}: {failure}") from failure

        for client in self.clients.values():
            refusals = client.refusals()
            if refusals:
                raise ScenarioError(f"{self.game_id}: {client.name} was refused: {refusals[0]}")

            expected = client.expected_refusals()
            if expected:
                raise ScenarioError(f"{self.game_id}: {client.name} was never refused with {expected[0]}")


@contextmanager
def seated_game(
    game_id: str,
    staged: StagedWall,
    *,
    players: Sequence[str],
    settings: GameSettings | None = None,
    later_rounds: Sequence[StagedWall] = (),
) -> Generator[SeatedGame]:
    """
    Open a SeatedGame on a loop of its own, dealt from the staged wall and then the later rounds' walls; on the way out
    stop the game and close the loop, whatever happened.
    """
    loop = VirtualTimeLoop()
    try:
        engine = _StagedEngine(staged, settings if settings is not None else GameSettings(), later_rounds)
        game = SeatedGame(loop, game_id, engine, players=players)
        try:
            yield game
        finally:
            game.stop()
    finally:
        loop.close()
