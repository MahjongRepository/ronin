from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.logic.enums import GameAction, KanType, PlayerAction, WaitKind
from game.logic.events import DrawEvent, ErrorEvent
from game.logic.mahjong_service import MahjongGameService
from game.logic.rng import RNG_VERSION
from game.logic.settings import GameSettings
from game.logic.shanten import calculate_shanten
from game.logic.tiles import hand_to_34_array
from game.replay import run_replay
from game.replay.loader import load_replay_from_string
from game.session.replay_collector import ReplayCollector, ReplayRecord
from game.tests.helpers.wall import make_start_wall
from game.tests.mocks.replay_storage import FakeReplayStorage
from game.wire.enums import WireEventType
from game.wire.replay_format import REPLAY_VERSION, ReplayLineType, ReplaySeatControlReason

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from game.logic.events import GameEvent
    from game.logic.state import MahjongGameState
    from game.replay.models import ReplayTrace

STAGED_SEED = "5" * 192
PLAYERS = ("Alice", "Bob", "Charlie", "Diana")
CALL_RESPONSES = frozenset({GameAction.CALL_PON, GameAction.CALL_CHI, GameAction.CALL_RON})


class ScenarioError(Exception):
    pass


@dataclass(frozen=True)
class Recording:
    """
    A fixture's replay lines, where each engine call's lines end, and the staged wall its first round was dealt from.

    call_ends are line counts: the replay as the server would have saved it after each call is that many lines. wall is
    None for a game dealt from its seed.
    """

    lines: tuple[str, ...]
    call_ends: tuple[int, ...]
    wall: tuple[int, ...] | None = None

    @property
    def text(self) -> str:
        return "\n".join([json.dumps({"version": REPLAY_VERSION}), *self.lines]) + "\n"

    def run(self) -> ReplayTrace:
        """
        Load the replay and run it through the replay runner on the same wall.
        """
        return run_replay(load_replay_from_string(self.text).model_copy(update={"wall": self.wall}))


class ReplayRecorder:
    """
    Record a game's events into replay lines one engine call at a time, as the session does.
    """

    def __init__(self, *, seed: str, settings: GameSettings) -> None:
        self._record = ReplayRecord(seed=seed, rng_version=RNG_VERSION, settings=settings)
        self._collector = ReplayCollector(FakeReplayStorage())
        self._call_ends: list[int] = []

    def record(self, events: Sequence[GameEvent]) -> None:
        self._collector.collect_events(self._record, list(events))
        self._call_ends.append(len(self._record.lines))

    def record_ai_replacement(self, *, seat: int, reason: ReplaySeatControlReason) -> None:
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
        self._call_ends.append(len(self._record.lines))

    def recording(self, wall: tuple[int, ...] | None = None) -> Recording:
        return Recording(lines=tuple(self._record.lines), call_ends=tuple(self._call_ends), wall=wall)


def require_reproduces(recording: Recording, final_state: MahjongGameState, *, name: str) -> None:
    """
    Raise ScenarioError unless the replay runner, given the recording, ends in the game's final state, its wait id
    aside.

    The wait id is a pacing counter the runner cannot reproduce: it plays each AI player's move within another seat's
    call as an action of its own, a wait of its own.
    """
    replayed = recording.run().final_state.model_copy(update={"wait_id": final_state.wait_id})
    if replayed != final_state:
        raise ScenarioError(f"{name}: the replay does not reproduce the game")


@dataclass(frozen=True)
class Outcome:
    """
    How a scenario's replay must end: the fields its last round end holds, and the line right after it.

    Fields match as a subset, nested mappings too, and a list matches item by item at its own length. then is the event
    or replay-only line type and fields of the line after the round end, or None when the round end is the replay's last
    line.
    """

    round_end: Mapping[str, object]
    then: tuple[WireEventType | ReplayLineType, Mapping[str, object]] | None = None


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
    Raise ScenarioError unless the replay's last round end, and the line after it, are the outcome's.
    """
    lines = [json.loads(line) for line in recording.lines]
    round_ends = [index for index, line in enumerate(lines) if line["t"] == WireEventType.ROUND_END]
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
    if not after or after[0]["t"] != event_type or not _holds(after[0], dict(fields)):
        raise ScenarioError(f"{name}: the line after the last round end is not a {event_type.name} with {fields}")


def cut_after(recording: Recording, *, event_type: WireEventType, occurrence: int) -> Recording:
    """
    Cut a replay after the engine call that holds its line of the event type at that occurrence.

    occurrence counts the event type's lines from zero, or from the end when negative. The cut falls between calls,
    since the server records a call's lines together and saves a replay only between calls; the cut replay must still
    load and run.
    """
    matches = [index for index, line in enumerate(recording.lines) if json.loads(line)["t"] == event_type]
    end = next(call_end for call_end in recording.call_ends if call_end > matches[occurrence])
    cut = Recording(
        lines=recording.lines[:end],
        call_ends=tuple(call_end for call_end in recording.call_ends if call_end <= end),
        wall=recording.wall,
    )
    cut.run()
    return cut


@dataclass(frozen=True)
class StagedWall:
    """
    The first round's wall of a staged game, with the first dealer at seat 0.

    hands are by seat; draws are the live wall's first draws as (seat, tile) pairs, each checked against the seat that
    draws it, and later live draws take the tiles nobody placed, in ascending id order; rinshan are the kan replacement
    tiles in draw order and ura the ura dora indicators in reveal order. Only the first round is staged: a later round
    is dealt from the recorded seed, which does not reproduce the first round's wall.
    """

    hands: Sequence[Sequence[int]]
    draws: Sequence[tuple[int, int]] = ()
    rinshan: Sequence[int] = ()
    ura: Sequence[int] = ()

    def tiles(self) -> tuple[int, ...]:
        return make_start_wall(self.hands, draws=[tile for _, tile in self.draws], rinshan=self.rinshan, ura=self.ura)


class _ScriptedGame:
    """
    A game of four players a script plays through the game service: every action must be accepted, and every event is
    recorded, a call at a time as the session would, with each seat's latest draw kept for the script.
    """

    def __init__(self, game_id: str, *, seed: str, settings: GameSettings, wall: tuple[int, ...] | None = None) -> None:
        self._game_id = game_id
        self._recorder = ReplayRecorder(seed=seed, settings=settings)
        self._service = MahjongGameService()
        start = self._service.start_game(
            game_id, list(PLAYERS), seed=seed, settings=settings, wall=None if wall is None else list(wall)
        )
        self._runtime = start.runtime
        self._draws: dict[int, DrawEvent] = {}
        self._record(start.events)

    def _run(self, seat: int, action: GameAction, data: dict[str, object]) -> None:
        events = self._service.handle_action(self._runtime, seat=seat, action=action, data=data).events
        errors = [event for event in events if isinstance(event, ErrorEvent)]
        if errors:
            raise ScenarioError(f"{self._game_id}: seat {seat} {action.value} refused: {errors[0].message}")

        self._draws.pop(seat, None)
        self._record(events)

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
    A game of four players dealt from a staged wall and played seat by seat.

    The game records every event the engine emits, a call at a time as the session would, and hands out the replay once
    it reproduces the game. Like the replay runner, an action that is not an answer to a pending call prompt first
    passes every seat the prompt waits on, but never a seat offered ron: a scenario declines a ron with pass_.
    """

    def __init__(self, game_id: str, staged: StagedWall, *, settings: GameSettings | None = None) -> None:
        self._staged_draws = tuple(staged.draws)
        self._next_staged_draw = 0
        self._wall = staged.tiles()
        super().__init__(
            game_id,
            seed=STAGED_SEED,
            settings=settings if settings is not None else GameSettings(),
            wall=self._wall,
        )

    def discard(self, seat: int, tile_id: int) -> None:
        self.act(seat, GameAction.DISCARD, tile_id=tile_id)

    def tsumogiri(self, seat: int) -> None:
        self.discard(seat, self._draw(seat).tile_id)

    def riichi(self, seat: int, tile_id: int | None = None) -> None:
        """
        Declare riichi with a discard of tile_id, or of the drawn tile when tile_id is None.
        """
        discard = tile_id if tile_id is not None else self._draw(seat).tile_id
        self.act(seat, GameAction.DECLARE_RIICHI, tile_id=discard)

    def pon(self, seat: int, tile_id: int) -> None:
        self.act(seat, GameAction.CALL_PON, tile_id=tile_id)

    def kan(self, seat: int, tile_id: int, kan_type: KanType) -> None:
        self.act(seat, GameAction.CALL_KAN, tile_id=tile_id, kan_type=kan_type)

    def tsumo(self, seat: int) -> None:
        self.act(seat, GameAction.DECLARE_TSUMO)

    def ron(self, *seats: int) -> None:
        """
        Declare ron for each seat, in order, on the pending discard or kan, after passing every other seat it waits on.

        A seat that is not declaring but was offered ron raises: decline it with pass_ first.
        """
        self._pass_calls(exclude=frozenset(seats))
        for seat in seats:
            self._run(seat, GameAction.CALL_RON, {})

    def kyuushu(self, seat: int) -> None:
        self.act(seat, GameAction.CALL_KYUUSHU)

    def replace_with_ai(self, seat: int, reason: ReplaySeatControlReason) -> None:
        """
        Hand the seat to an AI player, recorded as the session records it: its seat control line, then the events of the
        moves the AI player makes at once.

        From then on the engine plays the seat's turns and calls by itself.
        """
        if self._runtime.ai.is_ai_player(seat):
            raise ScenarioError(f"{self._game_id}: seat {seat} was replaced with an AI player twice")

        self._recorder.record_ai_replacement(seat=seat, reason=reason)
        self._service.replace_with_ai_player(self._runtime, seat)
        update = self._service.process_ai_player_actions_after_replacement(self._runtime, seat)
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
        self._run(seat, GameAction.PASS, {})

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
        Confirm the round end for every seat, which deals the next round.
        """
        for seat in sorted(self._service.get_awaiting(self._runtime).seats):
            self._run(seat, GameAction.CONFIRM_ROUND, {})

    def act(self, seat: int, action: GameAction, **data: object) -> None:
        is_call_response = action in CALL_RESPONSES or data.get("kan_type") == KanType.OPEN
        self._pass_calls(exclude=frozenset({seat}) if is_call_response else frozenset())
        self._run(seat, action, data)

    def replay(self, outcome: Outcome) -> Recording:
        """
        Return the recorded replay after checking that it ends in the outcome and that the replay runner, given the same
        wall, reproduces the game.

        The runner ends by passing a pending call prompt and confirming a pending round end, so the game does the same
        before the two final states are compared.
        """
        if self._next_staged_draw != len(self._staged_draws):
            raise ScenarioError(f"{self._game_id}: draw {self._next_staged_draw} and later were staged but not drawn")

        recording = self._recorder.recording(wall=self._wall)
        require_outcome(recording, outcome, name=self._game_id)
        self._pass_calls()
        if self._service.get_awaiting(self._runtime).kind == WaitKind.ROUND_ADVANCE:
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
        super().__init__(game_id, seed=seed, settings=GameSettings())

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
        if kind == WaitKind.ROUND_ADVANCE:
            for seat in sorted(seats):
                self._run(seat, GameAction.CONFIRM_ROUND, {})

            return

        if kind == WaitKind.CALL:
            prompt = self._runtime.state.round_state.pending_call_prompt
            seat = min(seats)
            can_ron = prompt is not None and prompt.caller(seat).can_ron
            self._run(seat, GameAction.CALL_RON if can_ron else GameAction.PASS, {})
            return

        (seat,) = seats
        draw = self._draws[seat]
        if PlayerAction.TSUMO in {item.action for item in draw.available_actions}:
            self._run(seat, GameAction.DECLARE_TSUMO, {})
            return

        self._run(seat, GameAction.DISCARD, {"tile_id": self._closest_to_ready_discard(seat, draw.tile_id)})

    def _closest_to_ready_discard(self, seat: int, drawn_tile: int) -> int:
        hand = self._runtime.state.round_state.players[seat].tiles

        def rank(tile_id: int) -> tuple[int, bool, int]:
            rest = list(hand)
            rest.remove(tile_id)
            return calculate_shanten(hand_to_34_array(rest)), tile_id != drawn_tile, -tile_id

        return min(hand, key=rank)
