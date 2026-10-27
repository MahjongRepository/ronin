from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from game.logic.enums import KanType
from game.replay import load_replay_from_file, run_replay
from game.replay.runner import ReplayOptions
from game.tests.helpers.hands import tile_copies
from game.wire.enums import WireEventType
from scripts.replay_fixtures.staged_game import (
    ReplayRecorder,
    StagedGame,
    StagedWall,
    cut_after,
    require_reproduces,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from scripts.replay_fixtures.staged_game import Recording

BACKEND_FULL_GAME = (
    Path(__file__).resolve().parents[2] / "game" / "tests" / "integration" / "replays" / "fixtures" / "full_round"
) / "full_game.txt"
BACKEND_FULL_GAME_ID = "fixture-fg"


def tile(copy: int, **suit: str) -> int:
    """
    Return the tile id of one copy of one tile, named as tile_copies names tiles (man="5", honors="7").
    """
    (tile_id,) = tile_copies(copy, **suit)
    return tile_id


def riichi() -> Recording:
    """
    Play a riichi on the drawn tile whose tile is ponned, a second riichi, and a riichi tsumo with ura dora.

    The riichi seat's discard after the pon is the one shown sideways; a red five is in the winning hand.
    """
    ponned_riichi_tile = tile(2, honors="7")
    second_riichi_tile = tile(0, honors="4")
    winning_tile = tile(1, sou="5")
    staged = StagedWall(
        hands=(
            (*tile_copies(3, man="18", pin="268", sou="168", honors="1234"), tile(0, man="5")),
            (*tile_copies(0, man="123", pin="456789", sou="349"), tile(1, sou="9")),
            (*tile_copies(2, man="147", pin="1", sou="147", honors="2356"), tile(0, honors="7"), tile(1, honors="7")),
            (*tile_copies(1, man="234", pin="234"), *tile_copies(0, man="678", sou="678"), second_riichi_tile),
        ),
        draws=(
            (0, tile(3, man="3")),
            (1, tile(1, man="9")),
            (2, tile(0, honors="3")),
            (3, tile(1, sou="1")),
            (0, tile(2, man="2")),
            (1, ponned_riichi_tile),
            (3, tile(1, pin="9")),
            (0, tile(0, honors="6")),
            (1, tile(0, pin="1")),
            (2, tile(0, man="4")),
            (3, tile(1, honors="6")),
            (0, tile(0, honors="2")),
            (1, winning_tile),
        ),
        ura=(tile(1, pin="8"),),
    )
    game = StagedGame("riichi", staged)
    game.discard(0, tile(3, honors="1"))
    game.tsumogiri(1)
    game.tsumogiri(2)
    game.tsumogiri(3)
    game.discard(0, tile(3, man="8"))
    game.riichi(1)
    game.pon(2, ponned_riichi_tile)
    game.discard(2, tile(2, honors="2"))
    game.riichi(3, second_riichi_tile)
    game.tsumogiri_until(1)
    game.tsumogiri(1)
    game.tsumogiri_until(1)
    game.tsumo(1)
    return game.replay()


@cache
def kans() -> Recording:
    """
    Play an open kan, a pon raised to an added kan and a closed kan, each with its dora, then a rinshan kaihou tsumo.
    """
    open_kan_tile = tile(3, honors="6")
    ponned_tile = tile(2, honors="5")
    added_kan_tile = tile(3, honors="5")
    closed_kan_tile = tile(3, sou="1")
    staged = StagedWall(
        hands=(
            (open_kan_tile, *tile_copies(1, man="147", pin="147", sou="258", honors="123")),
            (tile(0, honors="5"), tile(1, honors="5"), *tile_copies(1, man="258", pin="258", sou="369", honors="47")),
            (tile(0, honors="6"), tile(1, honors="6"), *tile_copies(2, man="36", pin="369", sou="479", honors="126")),
            (
                *(tile(copy, sou="1") for copy in range(3)),
                *tile_copies(0, man="234", pin="567", sou="678"),
                ponned_tile,
            ),
        ),
        draws=(
            (0, tile(2, honors="4")),
            (3, tile(0, man="9")),
            (2, tile(3, honors="2")),
            (3, tile(3, honors="3")),
            (0, tile(3, honors="4")),
            (1, added_kan_tile),
            (2, tile(2, honors="7")),
            (3, closed_kan_tile),
        ),
        rinshan=(tile(3, honors="7"), tile(3, man="3"), tile(1, man="9")),
    )
    game = StagedGame("kans", staged)
    game.discard(0, open_kan_tile)
    game.kan(2, open_kan_tile, KanType.OPEN)
    game.tsumogiri(2)
    game.discard(3, ponned_tile)
    game.pon(1, ponned_tile)
    game.discard(1, tile(1, honors="4"))
    game.tsumogiri_until(1)
    game.kan(1, added_kan_tile, KanType.ADDED)
    game.tsumogiri(1)
    game.tsumogiri_until(3)
    game.kan(3, closed_kan_tile, KanType.CLOSED)
    game.tsumo(3)
    return game.replay()


@cache
def full_game() -> Recording:
    """
    Run the backend's recorded full game (twelve rounds into the West round, dealt from its seed) and record it.
    """
    source = load_replay_from_file(BACKEND_FULL_GAME)
    trace = run_replay(source, ReplayOptions(game_id=BACKEND_FULL_GAME_ID))
    recorder = ReplayRecorder(seed=source.seed, settings=source.settings)
    recorder.record(trace.startup_events)
    for step in trace.steps:
        recorder.record(step.emitted_events)

    recording = recorder.recording()
    require_reproduces(recording, trace.final_state, name="full_game")
    return recording


def truncated_mid_round() -> Recording:
    """
    Cut kans after the closed kan's call (its meld, dora and replacement draw), before the rinshan kaihou tsumo.
    """
    return cut_after(kans(), event_type=WireEventType.DORA_REVEALED, occurrence=-1)


def truncated_after_round() -> Recording:
    return cut_after(full_game(), event_type=WireEventType.ROUND_END, occurrence=1)


FIXTURES: dict[str, Callable[[], Recording]] = {
    "riichi.txt": riichi,
    "kans.txt": kans,
    "full_game.txt": full_game,
    "truncated_mid_round.txt": truncated_mid_round,
    "truncated_after_round.txt": truncated_after_round,
}
