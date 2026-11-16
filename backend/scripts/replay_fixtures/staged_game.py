from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.engine import (
    NUM_PLAYERS,
    RNG_VERSION,
    Chi,
    Discard,
    DrawEvent,
    Kan,
    KanType,
    Kyuushu,
    MahjongGameService,
    Pass,
    PlayerAction,
    Pon,
    Refusal,
    Riichi,
    Ron,
    StartPosition,
    Tsumo,
    WaitKind,
    calculate_shanten,
    hand_to_34_array,
)
from game.replay import run_replay
from game.replay.loader import load_replay_from_bytes
from game.session.replay_collector import ReplayCollector, ReplayRecord
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.start_wall import make_start_wall
from game.tests.mocks.replay_storage import FakeReplayStorage
from game.wire.enums import SeatControlReason, WireEventType
from game.wire.keys import WireKey
from game.wire.replay_format import REPLAY_VERSION, ReplayLineType, decode_replay_records, encode_replay_records

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from game.engine import Action, GameEvent, GameUpdate, MahjongGameState
    from game.replay.models import ReplayTrace

STAGED_SEED = "5" * 192
PLAYERS = ("Alice", "Bob", "Charlie", "Diana")


class ScenarioError(Exception):
    pass


@dataclass(frozen=True)
class Recording:
    """
    A fixture's replay records, where each engine call's records end, and the setup the game was staged from: the walls
    its first rounds were dealt from and the position it started at.

    call_ends counts the records after each engine call. walls is empty for a game dealt from its seed, and start is
    None for a game started at East 1. Neither is a replay field: the replay runner is given them for the re-run.
    """

    records: tuple[dict[int, object], ...]
    call_ends: tuple[int, ...]
    walls: tuple[tuple[int, ...], ...] = ()
    start: StartPosition | None = None

    @property
    def content(self) -> bytes:
        return encode_replay_records([{WireKey.REPLAY_VERSION: REPLAY_VERSION}, *self.records])

    def run(self) -> ReplayTrace:
        """
        Load the replay and run it through the replay runner on the same walls and start position.
        """
        return run_replay(
            load_replay_from_bytes(self.content).model_copy(update={"walls": self.walls, "start": self.start})
        )


class ReplayRecorder:
    """
    Record a game's events into replay records one engine call at a time, as the session does, and keep the walls and
    start position the game was staged from for its recording.
    """

    def __init__(
        self,
        *,
        seed: str,
        walls: tuple[tuple[int, ...], ...] = (),
        start: StartPosition | None = None,
    ) -> None:
        self._record = ReplayRecord(seed=seed, rng_version=RNG_VERSION)
        self._walls = walls
        self._start = start
        self._collector = ReplayCollector(FakeReplayStorage())
        self._call_ends: list[int] = []

    def record(self, events: Sequence[GameEvent]) -> None:
        self._collector.collect_events(self._record, list(events))
        self._call_ends.append(len(self._record.records))

    def record_ai_replacement(self, *, seat: int, reason: SeatControlReason) -> None:
        """
        Record the seat's replacement with an AI player, ahead of the events of its moves, which the next record call
        adds.
        """
        self._collector.record_ai_replacement(self._record, seat=seat, reason=reason)

    def record_human_return(self, *, seat: int) -> None:
        """
        Record the seat's human return from its AI player: a session step of its own, after which the replay may be
        saved.
        """
        self._collector.record_human_return(self._record, seat=seat)
        self._call_ends.append(len(self._record.records))

    def recording(self) -> Recording:
        return Recording(
            records=tuple(self._record.records),
            call_ends=tuple(self._call_ends),
            walls=self._walls,
            start=self._start,
        )


def require_reproduces(recording: Recording, final_state: MahjongGameState, *, name: str) -> None:
    """
    Raise ScenarioError unless the replay runner, given the recording, ends in the game's final state.
    """
    if recording.run().final_state != final_state:
        raise ScenarioError(f"{name}: the replay does not reproduce the game")


@dataclass(frozen=True)
class Outcome:
    """
    How a scenario's replay must end: the fields its last round end holds, and the record right after it.

    Fields match as a subset, nested mappings too, and a list matches item by item at its own length. then is the event
    or replay-only record type and fields of the record after the round end, or None when the round end is the replay's
    last record.
    """

    round_end: Mapping[int, object]
    then: tuple[WireEventType | ReplayLineType, Mapping[int, object]] | None = None


def _holds(actual: object, expected: object) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _holds(actual[key], value) for key, value in expected.items()
        )

    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_holds(item, expected_item) for item, expected_item in zip(actual, expected, strict=True))
        )

    return actual == expected


def require_outcome(recording: Recording, outcome: Outcome, *, name: str) -> None:
    """
    Raise ScenarioError unless the replay's last round end, and the record after it, are the outcome's.
    """
    lines = decode_replay_records(recording.content)[1:]
    round_ends = [index for index, line in enumerate(lines) if line[WireKey.EVENT_TYPE] == WireEventType.ROUND_END]
    if not round_ends:
        raise ScenarioError(f"{name}: the replay has no round end")

    round_end, *after = lines[round_ends[-1] :]
    if not _holds(round_end, dict(outcome.round_end)):
        raise ScenarioError(f"{name}: the last round end {round_end} does not hold {dict(outcome.round_end)}")

    if outcome.then is None:
        if after:
            raise ScenarioError(f"{name}: the replay goes on after its last round end with {after[0]}")

        return

    event_type, fields = outcome.then
    if not after or after[0][WireKey.EVENT_TYPE] != event_type or not _holds(after[0], dict(fields)):
        raise ScenarioError(f"{name}: the record after the last round end is not a {event_type.name} with {fields}")


def cut_after(recording: Recording, *, event_type: WireEventType, occurrence: int) -> Recording:
    """
    Cut a replay after the engine call that holds its record of the event type at that occurrence.

    occurrence counts the event type's records from zero, or from the end when negative. The cut falls between calls,
    since the server records a call's records together and saves a replay only between calls; the cut replay must still
    load and run.
    """
    matches = [index for index, line in enumerate(recording.records) if line[WireKey.EVENT_TYPE] == event_type]
    end = next(call_end for call_end in recording.call_ends if call_end > matches[occurrence])
    cut = Recording(
        records=recording.records[:end],
        call_ends=tuple(call_end for call_end in recording.call_ends if call_end <= end),
        walls=recording.walls,
        start=recording.start,
    )
    cut.run()
    return cut


def tile(copy: int, **suit: str) -> int:
    """
    Return the tile id of one copy of one tile, named as tile_copies names tiles (man="5", honors="7").
    """
    (tile_id,) = tile_copies(copy, **suit)
    return tile_id


@dataclass(frozen=True)
class StagedWall:
    """
    A round's wall of a staged game, dealt from the dealer's seat: for the first round seat 0, or the start position's
    dealer.

    hands are by seat; draws are the live wall's first draws as (seat, tile) pairs (StagedGame and the seat scenarios'
    engine check each against the seat that draws it), and later live draws take the tiles nobody placed, in ascending
    id order; rinshan are the kan replacement tiles in draw order and ura the ura dora indicators in reveal order. A
    staged game stages only its first round: a later round is dealt from the recorded seed, which does not reproduce the
    first round's wall. The seat scenarios alone also stage a later round, with that round's dealer.
    """

    hands: Sequence[Sequence[int]]
    draws: Sequence[tuple[int, int]] = ()
    rinshan: Sequence[int] = ()
    ura: Sequence[int] = ()
    dealer: int = 0

    def tiles(self) -> tuple[int, ...]:
        in_deal_order = [self.hands[(self.dealer + offset) % NUM_PLAYERS] for offset in range(NUM_PLAYERS)]
        return make_start_wall(
            in_deal_order, draws=[tile for _, tile in self.draws], rinshan=self.rinshan, ura=self.ura
        )


@dataclass(frozen=True)
class Seating:
    """
    Who plays a scripted game: its players in input order, and the seats of those with no connection at the first deal.

    The engine seats AI players in the seats the players leave empty, as in a room of fewer than four. An absent seat is
    an AI player's from the deal, recorded as the session records it: its record after the deal and ahead of the
    dealer's first draw, its AI player's moves after them.
    """

    players: Sequence[str] = PLAYERS
    absent: frozenset[int] = frozenset()


FOUR_AT_THE_TABLE = Seating()


class _ScriptedGame:
    """
    A game a script plays through the game service: every action must be accepted, and every event is recorded, a call
    at a time as the session would, with each seat's latest draw kept for the script.
    """

    def __init__(
        self,
        game_id: str,
        *,
        seed: str,
        seating: Seating,
        walls: tuple[tuple[int, ...], ...] = (),
        start_position: StartPosition | None = None,
    ) -> None:
        self._game_id = game_id
        self._recorder = ReplayRecorder(seed=seed, walls=walls, start=start_position)
        self._service = MahjongGameService()
        start = self._service.start_game(game_id, list(seating.players), seed=seed, walls=walls, start=start_position)
        self._runtime = start.runtime
        self._draws: dict[int, DrawEvent] = {}
        if not seating.absent < set(start.seats):
            raise ScenarioError(
                f"{game_id}: absent seats {sorted(seating.absent)} are not some of the players' {start.seats}"
            )

        self._record(start.events)
        absent_in_player_order = [seat for seat in start.seats if seat in seating.absent]
        for seat in absent_in_player_order:
            self._service.replace_with_ai_player(self._runtime, seat)
            self._recorder.record_ai_replacement(seat=seat, reason=SeatControlReason.ABSENT)

        self._record(self._accepted(self._service.begin_round(self._runtime), "begin_round").events)

    def _run(self, seat: int, action: Action) -> None:
        update = self._accepted(self._service.act(self._runtime, seat, action), f"seat {seat} {action}")
        self._draws.pop(seat, None)
        self._record(update.events)

    def _accepted(self, result: GameUpdate | Refusal, call: str) -> GameUpdate:
        if isinstance(result, Refusal):
            raise ScenarioError(f"{self._game_id}: {call} refused: {result.kind.value}: {result.code.value}")

        return result

    def _advance_round(self) -> None:
        """
        Deal the next round after a round's end and let its dealer draw, recorded as the one step the session's pause
        ends in.
        """
        dealt = self._accepted(self._service.deal_next_round(self._runtime), "deal_next_round")
        begun = self._accepted(self._service.begin_round(self._runtime), "begin_round")
        self._record([*dealt.events, *begun.events])

    def _record(self, events: Sequence[GameEvent]) -> None:
        self._recorder.record(events)
        for event in events:
            if isinstance(event, DrawEvent):
                self._check_draw(event)
                self._draws[event.seat] = event

    def _check_draw(self, draw: DrawEvent) -> None:
        """
        Check a draw before the script sees it; any draw goes by default.
        """


class StagedGame(_ScriptedGame):
    """
    A game dealt from a staged wall and played seat by seat, by four players unless fewer are given, from East 1 or from
    the start position when one is given.

    The staged seed seats the players in order at seats 1, 3, 2 and 0, so three players leave the dealer's seat to an AI
    player. The game records every event the engine emits, a call at a time as the session would, and hands out the
    replay once it reproduces the game. Like the replay runner, an action that is not an answer to a pending call prompt
    first passes every seat the prompt waits on, but never a seat offered ron: a scenario declines a ron with pass_.
    """

    def __init__(
        self,
        game_id: str,
        staged: StagedWall,
        *,
        seating: Seating = FOUR_AT_THE_TABLE,
        start: StartPosition | None = None,
    ) -> None:
        dealer = start.dealer_seat if start is not None else 0
        if staged.dealer != dealer:
            raise ScenarioError(
                f"{game_id}: a staged game's first round is dealt from seat {dealer}, not {staged.dealer}"
            )

        self._staged_draws = tuple(staged.draws)
        self._next_staged_draw = 0
        super().__init__(
            game_id,
            seed=STAGED_SEED,
            seating=seating,
            walls=(staged.tiles(),),
            start_position=start,
        )

    def discard(self, seat: int, tile_id: int) -> None:
        self.act(seat, Discard(tile=tile_id))

    def tsumogiri(self, seat: int) -> None:
        self.discard(seat, self._draw(seat).tile_id)

    def riichi(self, seat: int, tile_id: int | None = None) -> None:
        """
        Declare riichi with a discard of tile_id, or of the drawn tile when tile_id is None.
        """
        discard = tile_id if tile_id is not None else self._draw(seat).tile_id
        self.act(seat, Riichi(tile=discard))

    def pon(self, seat: int) -> None:
        self.act(seat, Pon())

    def kan(self, seat: int, tile_id: int, kan_type: KanType) -> None:
        self.act(seat, Kan(kan_type=kan_type, tile=tile_id))

    def tsumo(self, seat: int) -> None:
        self.act(seat, Tsumo())

    def ron(self, *seats: int) -> None:
        """
        Declare ron for each seat, in order, on the pending discard or kan, after passing every other seat it waits on.

        A seat that is not declaring but was offered ron raises: decline it with pass_ first.
        """
        self._pass_calls(exclude=frozenset(seats))
        for seat in seats:
            self._run(seat, Ron())

    def kyuushu(self, seat: int) -> None:
        self.act(seat, Kyuushu())

    def leave(self, seat: int) -> None:
        """
        Hand the seat of a player who left to an AI player, recorded as the session records it: its seat control record,
        then the events of the moves the AI player makes at once.

        From then on the engine plays the seat's turns and calls by itself.
        """
        if self._runtime.ai.is_ai_player(seat):
            raise ScenarioError(f"{self._game_id}: seat {seat} was replaced with an AI player twice")

        self._service.replace_with_ai_player(self._runtime, seat)
        update = self._service.process_ai_player_actions_after_replacement(self._runtime, seat)
        self._recorder.record_ai_replacement(seat=seat, reason=SeatControlReason.LEFT)
        self._record(update.events)

    def restore_human(self, seat: int) -> None:
        """
        Return the seat from its AI player to its participant, recorded as the session records a reconnect.
        """
        if not self._runtime.ai.is_ai_player(seat):
            raise ScenarioError(f"{self._game_id}: seat {seat} was restored without an AI player in it")

        self._service.restore_human_player(self._runtime, seat)
        self._recorder.record_human_return(seat=seat)

    def pass_(self, seat: int) -> None:
        """
        Decline the pending call prompt for the seat, a ron included.
        """
        self._run(seat, Pass())

    def tsumogiri_until(self, seat: int | None = None) -> None:
        """
        Discard each drawn tile and pass every call prompt until it is the seat's turn, or the round ends when seat is
        None.

        A turn that offers a tsumo raises: discarding the winning tile is a decision the scenario makes itself.
        """
        while True:
            self._pass_calls()
            awaiting = self._service.get_awaiting(self._runtime)
            if awaiting.kind != WaitKind.TURN:
                if seat is None:
                    return

                raise ScenarioError(f"{self._game_id}: the round ended before seat {seat}'s turn")

            (current,) = awaiting.seats
            if current == seat:
                return

            offers = {item.action for item in self._draw(current).available_actions}
            if PlayerAction.TSUMO in offers:
                raise ScenarioError(f"{self._game_id}: seat {current} was offered tsumo while discarding draws")

            self.tsumogiri(current)

    def confirm_round(self) -> None:
        """
        Let every seat confirm the round end, as the session's pause does, which deals the next round and lets its
        dealer draw.
        """
        self._advance_round()

    def act(self, seat: int, action: Action) -> None:
        is_open_kan = isinstance(action, Kan) and action.kan_type == KanType.OPEN
        is_call_response = isinstance(action, Pon | Chi | Ron) or is_open_kan
        self._pass_calls(exclude=frozenset({seat}) if is_call_response else frozenset())
        self._run(seat, action)

    def replay(self, outcome: Outcome) -> Recording:
        """
        Return the recorded replay after checking that it ends in the outcome and that the replay runner, given the same
        wall and start position, reproduces the game.

        The runner ends by passing a pending call prompt and advancing past a round end, so the game does the same
        before the two final states are compared.
        """
        if self._next_staged_draw != len(self._staged_draws):
            raise ScenarioError(f"{self._game_id}: draw {self._next_staged_draw} and later were staged but not drawn")

        recording = self._recorder.recording()
        require_outcome(recording, outcome, name=self._game_id)
        self._pass_calls()
        if self._service.get_awaiting(self._runtime).kind == WaitKind.ROUND_OVER:
            self.confirm_round()

        require_reproduces(recording, self._runtime.state, name=self._game_id)
        return recording

    def _draw(self, seat: int) -> DrawEvent:
        if seat not in self._draws:
            raise ScenarioError(f"{self._game_id}: seat {seat} has no drawn tile")

        return self._draws[seat]

    def _pass_calls(self, exclude: frozenset[int] = frozenset()) -> None:
        prompt = self._runtime.state.round_state.pending_call_prompt
        if prompt is None:
            return

        for seat in sorted(prompt.pending_seats - exclude):
            if prompt.caller(seat).can_ron:
                raise ScenarioError(f"{self._game_id}: seat {seat} was offered ron; pass_ it or call it")

            self.pass_(seat)

    def _check_draw(self, draw: DrawEvent) -> None:
        """
        Check a draw of a staged tile against the seat the scenario staged it for; other draws are rinshan or filler.
        """
        staged = [index for index, (_, tile_id) in enumerate(self._staged_draws) if tile_id == draw.tile_id]
        if not staged:
            return

        (index,) = staged
        seat = self._staged_draws[index][0]
        if index != self._next_staged_draw or draw.seat != seat:
            raise ScenarioError(
                f"{self._game_id}: seat {draw.seat} drew staged draw {index} (staged for seat {seat}) as draw "
                f"{self._next_staged_draw}"
            )

        self._next_staged_draw += 1


class EagerGame(_ScriptedGame):
    """
    A game of four players dealt from its seed and played to its end by a fixed policy: a seat wins whenever it is
    offered a tsumo or a ron, passes every other call, and otherwise discards the tile that leaves its hand closest to
    ready (its drawn tile on a tie, then the highest tile id).

    The policy makes no call and declares no riichi, so the game holds wins in many rounds under every dealer.
    """

    def __init__(self, game_id: str, seed: str) -> None:
        super().__init__(game_id, seed=seed, seating=FOUR_AT_THE_TABLE)

    def replay(self, outcome: Outcome) -> Recording:
        """
        Play the game to its end and return the recorded replay, after checking that it ends in the outcome and that the
        replay runner reproduces the game.
        """
        while (awaiting := self._service.get_awaiting(self._runtime)).kind != WaitKind.NONE:
            self._act(awaiting.kind, awaiting.seats)

        recording = self._recorder.recording()
        require_outcome(recording, outcome, name=self._game_id)
        require_reproduces(recording, self._runtime.state, name=self._game_id)
        return recording

    def _act(self, kind: WaitKind, seats: frozenset[int]) -> None:
        if kind == WaitKind.ROUND_OVER:
            self._advance_round()
            return

        if kind == WaitKind.CALL:
            prompt = self._runtime.state.round_state.pending_call_prompt
            seat = min(seats)
            can_ron = prompt is not None and prompt.caller(seat).can_ron
            self._run(seat, Ron() if can_ron else Pass())
            return

        (seat,) = seats
        draw = self._draws[seat]
        if PlayerAction.TSUMO in {item.action for item in draw.available_actions}:
            self._run(seat, Tsumo())
            return

        self._run(seat, Discard(tile=self._closest_to_ready_discard(seat, draw.tile_id)))

    def _closest_to_ready_discard(self, seat: int, drawn_tile: int) -> int:
        hand = self._runtime.state.round_state.players[seat].tiles

        def rank(tile_id: int) -> tuple[int, bool, int]:
            rest = list(hand)
            rest.remove(tile_id)
            return calculate_shanten(hand_to_34_array(rest)), tile_id != drawn_tile, -tile_id

        return min(hand, key=rank)
