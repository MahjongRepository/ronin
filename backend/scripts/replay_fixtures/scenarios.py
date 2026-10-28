from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from game.logic.enums import AbortiveDrawType, KanType
from game.logic.settings import NUM_PLAYERS, GameSettings
from game.logic.tiles import NUM_TILES, is_terminal_or_honor, tile_to_34
from game.replay import load_replay_from_file, run_replay
from game.replay.runner import ReplayOptions
from game.tests.helpers.hands import (
    PIN_3_TRIPLE_RON_CALLER_HANDS,
    PIN_3_TRIPLE_RON_DEALER_HAND,
    PIN_3_TRIPLE_RON_DISCARD,
    tile_copies,
)
from game.tests.helpers.wall import DEAD_WALL_START, FIRST_DRAW_POSITION
from game.wire.enums import WireEventType, WireRoundResultType
from game.wire.replay_format import ReplayLineType, ReplaySeatControlReason
from scripts.replay_fixtures.staged_game import (
    EagerGame,
    Outcome,
    ReplayRecorder,
    ScenarioError,
    StagedGame,
    StagedWall,
    cut_after,
    require_outcome,
    require_reproduces,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from scripts.replay_fixtures.staged_game import Recording

BACKEND_FULL_GAME = (
    Path(__file__).resolve().parents[2] / "game" / "tests" / "integration" / "replays" / "fixtures" / "full_round"
) / "full_game.txt"
BACKEND_FULL_GAME_ID = "fixture-fg"
EAGER_GAME_SEED = "09" * 96
EAGER_DOUBLE_RON_SEED = "033c" * 48
GAME_ENDS = (WireEventType.GAME_END, {})


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
    return game.replay(Outcome({"rt": WireRoundResultType.TSUMO, "ws": 1, "ud": [tile(1, pin="8")]}))


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
    return game.replay(Outcome({"rt": WireRoundResultType.TSUMO, "ws": 3}))


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
    require_outcome(recording, Outcome({"rt": WireRoundResultType.EXHAUSTIVE_DRAW}, then=GAME_ENDS), name="full_game")
    require_reproduces(recording, trace.final_state, name="full_game")
    return recording


def ron_riichi_discard() -> Recording:
    """
    Ron a riichi declaration's discard by a riichi player: the discarder's stick is never deposited, ura dora show.
    """
    riichi_discard = tile(1, pin="4")
    staged = StagedWall(
        hands=(
            tile_copies(2, man="1", pin="1569", sou="1589", honors="1234"),
            tile_copies(0, man="123456789", pin="23", sou="11"),
            (*tile_copies(0, sou="234567", pin="789"), *tile_copies(1, man="5567")),
            tile_copies(3, man="1", pin="1569", sou="1589", honors="1234"),
        ),
        draws=((0, tile(0, honors="5")), (1, tile(0, honors="6")), (2, riichi_discard)),
    )
    game = StagedGame("ron-riichi-discard", staged)
    game.tsumogiri(0)
    game.riichi(1)
    game.riichi(2)
    game.ron(1)
    return game.replay(Outcome({"rt": WireRoundResultType.RON, "ws": 1, "ls": 2, "rc": 1}))


def double_ron() -> Recording:
    """
    Ron the dealer's discard by two riichi players; the one nearer the discarder takes both riichi sticks.
    """
    winning_tile = tile(2, pin="4")
    staged = StagedWall(
        hands=(
            tile_copies(2, man="178", pin="129", sou="159", honors="1234"),
            tile_copies(0, man="123456789", pin="23", sou="11"),
            tile_copies(1, man="23499", pin="56", sou="456678"),
            tile_copies(3, man="178", pin="129", sou="159", honors="1234"),
        ),
        draws=(
            (0, tile(0, honors="5")),
            (1, tile(0, honors="6")),
            (2, tile(0, honors="7")),
            (3, tile(1, honors="5")),
            (0, winning_tile),
        ),
    )
    game = StagedGame("double-ron", staged)
    game.tsumogiri(0)
    game.riichi(1)
    game.riichi(2)
    game.tsumogiri(3)
    game.tsumogiri(0)
    game.ron(1, 2)
    return game.replay(
        Outcome({"rt": WireRoundResultType.DOUBLE_RON, "ls": 0, "wn": [{"ws": 1, "rc": 2}, {"ws": 2, "rc": 0}]})
    )


def _pin_3_multi_ron(game_id: str, settings: GameSettings, *, callers: tuple[int, ...], outcome: Outcome) -> Recording:
    """
    Discard the dealer's 3p into three hands waiting on it; the callers declare ron and every other seat passes.
    """
    staged = StagedWall(
        hands=(PIN_3_TRIPLE_RON_DEALER_HAND, *PIN_3_TRIPLE_RON_CALLER_HANDS),
        draws=((0, PIN_3_TRIPLE_RON_DISCARD),),
    )
    game = StagedGame(game_id, staged, settings=settings)
    game.discard(0, PIN_3_TRIPLE_RON_DISCARD)
    for seat in (1, 2, 3):
        if seat not in callers:
            game.pass_(seat)

    game.ron(*callers)
    return game.replay(outcome)


def triple_ron() -> Recording:
    """
    Ron one discard by three callers, which aborts the round with no score change.
    """
    return _pin_3_multi_ron(
        "triple-ron",
        GameSettings(),
        callers=(1, 2, 3),
        outcome=Outcome({"rt": WireRoundResultType.ABORTIVE_DRAW, "rn": AbortiveDrawType.TRIPLE_RON, "rcl": [1, 2, 3]}),
    )


def double_ron_head_bump() -> Recording:
    """
    Ron one discard by three callers with the triple ron abort off: the two nearest win and the third is head-bumped.

    The dealer pays both wins and drops below zero, so the fixture ends the game.
    """
    return _pin_3_multi_ron(
        "double-ron-head-bump",
        GameSettings(has_triple_ron_abort=False),
        callers=(1, 2, 3),
        outcome=Outcome(
            {"rt": WireRoundResultType.DOUBLE_RON, "wn": [{"ws": 1}, {"ws": 2}], "hbs": [3]}, then=GAME_ENDS
        ),
    )


def head_bump() -> Recording:
    """
    Ron one discard by two callers with double ron off: the nearer one wins and the other is head-bumped.
    """
    return _pin_3_multi_ron(
        "head-bump",
        GameSettings(has_double_ron=False),
        callers=(1, 2),
        outcome=Outcome({"rt": WireRoundResultType.RON, "ws": 1, "hbs": [2]}),
    )


def chankan_added() -> Recording:
    """
    Raise a pon of 6p to an added kan that a hand waiting on 6p robs.
    """
    ponned_tile = tile(2, pin="6")
    added_kan_tile = tile(3, pin="6")
    staged = StagedWall(
        hands=(
            (*tile_copies(2, man="258", pin="17", sou="369", honors="1234"), ponned_tile),
            (*tile_copies(0, pin="66"), *tile_copies(1, man="147", pin="19", sou="258", honors="123")),
            tile_copies(0, man="123456789", pin="45", sou="19"),
            tile_copies(3, man="258", pin="17", sou="369", honors="12345"),
        ),
        draws=(
            (0, tile(0, honors="7")),
            (2, tile(1, sou="1")),
            (3, tile(1, honors="7")),
            (0, tile(2, honors="7")),
            (1, added_kan_tile),
        ),
    )
    game = StagedGame("chankan-added", staged)
    game.discard(0, ponned_tile)
    game.pon(1, ponned_tile)
    game.discard(1, tile(1, honors="1"))
    game.discard(2, tile(0, sou="9"))
    game.tsumogiri(3)
    game.tsumogiri(0)
    game.kan(1, added_kan_tile, KanType.ADDED)
    game.ron(2)
    return game.replay(Outcome({"rt": WireRoundResultType.RON, "ws": 2, "rk": {"s": 1, "kty": KanType.ADDED}}))


def chankan_ai_replacement() -> Recording:
    """
    Raise a pon of 6p to an added kan that two hands waiting on 6p may rob: seat 3 leaves during the chankan prompt, its
    AI player passes, then seat 2 robs it.

    Seat 3 is one tile from ready until its draw, so the pon's 6p offers it no ron.
    """
    ponned_tile = tile(2, pin="6")
    added_kan_tile = tile(3, pin="6")
    readying_tile = tile(3, pin="5")
    staged = StagedWall(
        hands=(
            (*tile_copies(2, man="258", pin="17", sou="369", honors="1234"), ponned_tile),
            (*tile_copies(0, pin="66"), *tile_copies(1, man="147", pin="19", sou="258", honors="123")),
            tile_copies(0, man="123456789", pin="45", sou="19"),
            (*tile_copies(3, man="234567", sou="456", pin="4", honors="1"), *tile_copies(0, honors="55")),
        ),
        draws=(
            (0, tile(0, honors="7")),
            (2, tile(1, sou="1")),
            (3, readying_tile),
            (0, tile(2, honors="7")),
            (1, added_kan_tile),
        ),
    )
    game = StagedGame("chankan-ai-replacement", staged)
    game.discard(0, ponned_tile)
    game.pon(1, ponned_tile)
    game.discard(1, tile(1, honors="1"))
    game.discard(2, tile(0, sou="9"))
    game.discard(3, tile(3, honors="1"))
    game.tsumogiri(0)
    game.kan(1, added_kan_tile, KanType.ADDED)
    game.replace_with_ai(3, ReplaySeatControlReason.LEFT)
    game.ron(2)
    return game.replay(Outcome({"rt": WireRoundResultType.RON, "ws": 2, "rk": {"s": 1, "kty": KanType.ADDED}}))


def chankan_closed_kokushi() -> Recording:
    """
    Declare a closed kan of 9m that a kokushi musou hand waiting on 9m robs.

    The kan's declarer pays the yakuman and drops below zero, so the fixture ends the game.
    """
    closed_kan_tile = tile(3, man="9")
    staged = StagedWall(
        hands=(
            tile_copies(2, man="357", pin="357", sou="35789", honors="12"),
            (*tile_copies(0, man="999"), *tile_copies(1, man="246", pin="2468", sou="246")),
            tile_copies(0, man="11", pin="19", sou="19", honors="1234567"),
            tile_copies(3, man="357", pin="357", sou="35789", honors="12"),
        ),
        draws=(
            (0, tile(1, honors="3")),
            (1, tile(1, honors="4")),
            (2, tile(1, honors="5")),
            (3, tile(1, honors="6")),
            (0, tile(1, honors="7")),
            (1, closed_kan_tile),
        ),
    )
    game = StagedGame("chankan-closed-kokushi", staged)
    game.tsumogiri_until(1)
    game.tsumogiri(1)
    game.tsumogiri_until(1)
    game.kan(1, closed_kan_tile, KanType.CLOSED)
    game.ron(2)
    return game.replay(
        Outcome({"rt": WireRoundResultType.RON, "ws": 2, "rk": {"s": 1, "kty": KanType.CLOSED}}, then=GAME_ENDS)
    )


def pao() -> Recording:
    """
    Pon all three dragons, the last from the dealer, who becomes liable for the daisangen tsumo that follows.

    The dealer pays the whole yakuman and drops below zero, so the fixture ends the game.
    """
    first_dragon = tile(2, honors="5")
    second_dragon = tile(2, honors="6")
    liable_dragon = tile(2, honors="7")
    staged = StagedWall(
        hands=(
            (*tile_copies(2, man="258", pin="258", sou="258", honors="12"), first_dragon, liable_dragon),
            tile_copies(0, honors="556677", man="1234", pin="9", sou="19"),
            (*tile_copies(1, man="258", pin="258", sou="258", honors="123"), second_dragon),
            (*tile_copies(3, man="258", pin="258", sou="258", honors="123"), tile(3, sou="9")),
        ),
        draws=(
            (0, tile(1, pin="1")),
            (2, tile(2, pin="1")),
            (2, tile(3, pin="1")),
            (3, tile(1, man="9")),
            (0, tile(2, man="9")),
            (2, tile(3, man="9")),
            (3, tile(0, pin="3")),
            (0, tile(1, pin="3")),
            (1, tile(1, man="4")),
        ),
    )
    game = StagedGame("pao", staged)
    game.discard(0, first_dragon)
    game.pon(1, first_dragon)
    game.discard(1, tile(0, pin="9"))
    game.discard(2, second_dragon)
    game.pon(1, second_dragon)
    game.discard(1, tile(0, sou="1"))
    game.tsumogiri_until(0)
    game.discard(0, liable_dragon)
    game.pon(1, liable_dragon)
    game.discard(1, tile(0, sou="9"))
    game.tsumogiri_until(1)
    game.tsumo(1)
    return game.replay(Outcome({"rt": WireRoundResultType.TSUMO, "ws": 1, "ps": 0}, then=GAME_ENDS))


def exhaustive_tenpai() -> Recording:
    """
    Play a round out to an exhaustive draw with two tenpai hands, one in riichi, then deal the next round.

    Both tenpai hands wait on a tile whose other copies sit in a noten hand, so no discard of the wall can be won; the
    riichi stick and the honba carry into the second round's deal.
    """
    staged = StagedWall(
        hands=(
            (*tile_copies(0, honors="777"), *tile_copies(0, man="147", pin="147", sou="258", honors="1")),
            (*tile_copies(1, pin="123456789", sou="111"), tile(3, honors="7")),
            (*tile_copies(2, man="234567", sou="345678"), tile(3, honors="6")),
            (*tile_copies(0, honors="666"), *tile_copies(3, man="258", pin="258", sou="369", honors="2")),
        ),
    )
    game = StagedGame("exhaustive-tenpai", staged)
    game.tsumogiri(0)
    game.riichi(1)
    game.tsumogiri_until()
    game.confirm_round()
    return game.replay(
        Outcome(
            {"rt": WireRoundResultType.EXHAUSTIVE_DRAW, "ts": [1, 2], "ns": [0, 3]},
            then=(WireEventType.ROUND_STARTED, {"dl": 1, "h": 1, "r": 1}),
        )
    )


def nagashi() -> Recording:
    """
    Play a round out with every draw of seat 1 a terminal or honor, so its discards make a nagashi mangan.

    The four hands never change, since each seat discards what it draws: three are noten and seat 3 waits on a tile
    whose other copies sit in the dealer's hand, so no draw or discard can be won.
    """
    hands = (
        (*tile_copies(0, honors="555"), *tile_copies(0, man="258", pin="258", sou="258", honors="1")),
        tile_copies(1, man="23468", pin="2468", sou="2468"),
        tile_copies(2, man="2468", pin="2468", sou="2468", honors="2"),
        (*tile_copies(3, man="234567", sou="234567"), tile(3, honors="5")),
    )
    nagashi_seat = 1
    live_wall_draws = DEAD_WALL_START - FIRST_DRAW_POSITION
    draw_seats = [index % NUM_PLAYERS for index in range(live_wall_draws)]
    dealt = {tile_id for hand in hands for tile_id in hand}
    undealt = [tile_id for tile_id in range(NUM_TILES) if tile_id not in dealt]
    terminals_and_honors = [tile_id for tile_id in undealt if is_terminal_or_honor(tile_to_34(tile_id))]
    qualifying = terminals_and_honors[: draw_seats.count(nagashi_seat)]
    qualifying_draws = iter(qualifying)
    other_draws = iter(tile_id for tile_id in undealt if tile_id not in qualifying)
    draws = [(seat, next(qualifying_draws) if seat == nagashi_seat else next(other_draws)) for seat in draw_seats]
    game = StagedGame("nagashi", StagedWall(hands=hands, draws=draws))
    game.tsumogiri_until()
    return game.replay(Outcome({"rt": WireRoundResultType.NAGASHI_MANGAN, "qs": [nagashi_seat]}))


def kyuushu() -> Recording:
    """
    Abort the round by kyuushu kyuuhai on seat 1's first draw, with eleven terminal and honor types.
    """
    staged = StagedWall(
        hands=(
            (*tile_copies(1, man="258", pin="258", sou="258", honors="567"), tile(1, man="4")),
            tile_copies(0, man="19234", pin="19", sou="19", honors="1234"),
            (*tile_copies(2, man="258", pin="258", sou="258", honors="567"), tile(2, man="4")),
            (*tile_copies(3, man="258", pin="258", sou="258", honors="567"), tile(3, man="4")),
        ),
        draws=((0, tile(0, honors="6")), (1, tile(0, honors="5"))),
    )
    game = StagedGame("kyuushu", staged)
    game.tsumogiri(0)
    game.kyuushu(1)
    return game.replay(
        Outcome({"rt": WireRoundResultType.ABORTIVE_DRAW, "rn": AbortiveDrawType.NINE_TERMINALS, "s": 1})
    )


def four_winds_riichi() -> Recording:
    """
    Discard East from every seat on the first go-around, the last one declaring double riichi, which is never paid.
    """
    winds = tile_copies(0, honors="1111")
    staged = StagedWall(
        hands=(
            *(
                (winds[seat], *tile_copies(seat + 1, man="258", pin="169", sou="258", honors="567"))
                for seat in range(3)
            ),
            (*tile_copies(0, man="123456789", pin="223"), winds[3]),
        ),
        draws=(
            (0, tile(0, honors="2")),
            (1, tile(1, honors="2")),
            (2, tile(2, honors="2")),
            (3, tile(0, pin="4")),
        ),
    )
    game = StagedGame("four-winds-riichi", staged)
    for seat in range(3):
        game.discard(seat, winds[seat])

    game.riichi(3, winds[3])
    return game.replay(Outcome({"rt": WireRoundResultType.ABORTIVE_DRAW, "rn": AbortiveDrawType.FOUR_WINDS}))


def four_riichi() -> Recording:
    """
    Declare riichi from all four seats on their first discards.
    """
    staged = StagedWall(
        hands=(
            tile_copies(0, man="123456789", pin="23", honors="55"),
            tile_copies(1, man="123456789", sou="23", honors="66"),
            tile_copies(2, pin="123456789", sou="67", honors="77"),
            (*tile_copies(3, sou="123456789", pin="67"), *tile_copies(2, honors="55")),
        ),
        draws=tuple((seat, tile(0, honors=str(seat + 1))) for seat in range(NUM_PLAYERS)),
    )
    game = StagedGame("four-riichi", staged)
    for seat in range(NUM_PLAYERS):
        game.riichi(seat)

    return game.replay(Outcome({"rt": WireRoundResultType.ABORTIVE_DRAW, "rn": AbortiveDrawType.FOUR_RIICHI}))


def four_kans() -> Recording:
    """
    Declare two closed kans from the dealer, then a closed kan and an open kan from seat 1.

    The open kan is the fourth by two players: its replacement discard passes, its deferred dora is revealed and the
    round aborts.
    """
    open_kan_tile = tile(3, pin="7")
    staged = StagedWall(
        hands=(
            (*tile_copies(0, man="11112222"), *tile_copies(0, pin="19", sou="19", honors="1")),
            (*tile_copies(0, pin="3333777"), *tile_copies(1, sou="2468", honors="23")),
            tile_copies(2, man="369", pin="258", sou="369", honors="4567"),
            tile_copies(3, man="369", pin="258", sou="369", honors="4567"),
        ),
        draws=((0, tile(0, honors="2")), (1, tile(2, honors="3")), (2, open_kan_tile)),
        rinshan=(tile(0, man="8"), tile(1, man="8"), tile(0, pin="6"), tile(0, pin="4")),
    )
    game = StagedGame("four-kans", staged)
    game.kan(0, tile(0, man="1"), KanType.CLOSED)
    game.kan(0, tile(0, man="2"), KanType.CLOSED)
    game.tsumogiri(0)
    game.kan(1, tile(0, pin="3"), KanType.CLOSED)
    game.tsumogiri(1)
    game.tsumogiri(2)
    game.kan(1, open_kan_tile, KanType.OPEN)
    game.tsumogiri(1)
    return game.replay(Outcome({"rt": WireRoundResultType.ABORTIVE_DRAW, "rn": AbortiveDrawType.FOUR_KANS}))


def ai_replacements() -> Recording:
    """
    Replace seat 3, absent at the deal, with an AI player, which declines a pon of haku within seat 1's discard; then
    seat 2 on its turn, whose AI player discards the 4p that seat 1 rons.

    During the round advance seat 3's human returns and seat 0 leaves, its AI player confirming for it; in the next
    round seat 2's human returns after the dealer's draw, and seat 0's AI player draws and discards within seat 3's
    discard.
    """
    winning_tile = tile(1, pin="4")
    staged = StagedWall(
        hands=(
            tile_copies(2, man="1", pin="1569", sou="1589", honors="1234"),
            tile_copies(0, man="123456789", pin="23", sou="11"),
            (*tile_copies(0, sou="234567", pin="789"), *tile_copies(1, man="5567")),
            (*tile_copies(3, man="1", pin="1569", sou="1589", honors="12"), *tile_copies(0, honors="55")),
        ),
        draws=((0, tile(0, honors="6")), (1, tile(2, honors="5")), (2, winning_tile)),
    )
    game = StagedGame("ai-replacements", staged)
    game.replace_with_ai(3, ReplaySeatControlReason.ABSENT)
    game.tsumogiri(0)
    game.tsumogiri(1)
    game.replace_with_ai(2, ReplaySeatControlReason.LEFT)
    game.ron(1)
    game.restore_human(3)
    game.replace_with_ai(0, ReplaySeatControlReason.LEFT)
    game.confirm_round()
    game.restore_human(2)
    game.tsumogiri(1)
    game.tsumogiri(2)
    game.tsumogiri(3)
    return game.replay(
        Outcome(
            {"rt": WireRoundResultType.RON, "ws": 1, "ls": 2},
            then=(ReplayLineType.SEAT_CONTROL, {"s": 3, "ai": 0}),
        )
    )


def require_wins_off_seat_zero(recording: Recording, *, name: str) -> None:
    """
    Raise ScenarioError unless the replay holds a tsumo and a ron in rounds dealt by a seat other than 0.

    A staged game always deals its first round from seat 0, where a seat and its place counted from the dealer agree.
    """
    dealer: int | None = None
    results: set[int] = set()
    for line in map(json.loads, recording.lines):
        if line["t"] == WireEventType.ROUND_STARTED:
            dealer = line["dl"]
        elif line["t"] == WireEventType.ROUND_END and dealer != 0:
            results.add(line["rt"])

    if not {WireRoundResultType.TSUMO, WireRoundResultType.RON} <= results:
        raise ScenarioError(f"{name}: no tsumo and ron both in rounds dealt by a seat other than 0")


def eager_game() -> Recording:
    """
    Play a game dealt from its seed to its end, every seat winning whenever it may, with tsumos and rons under dealers
    other than seat 0.
    """
    recording = EagerGame("eager-game", EAGER_GAME_SEED).replay(
        Outcome({"rt": WireRoundResultType.TSUMO, "ws": 3}, then=GAME_ENDS)
    )
    require_wins_off_seat_zero(recording, name="eager_game")
    return recording


def double_ron_on_honba() -> Recording:
    """
    Play eager_game's policy from a seed whose third round, on two honba, ends in a double ron, to the next round's end.

    Each winner takes the two honba's 600 on top of a 1600 hand, so the discarder pays 4400.
    """
    game = EagerGame("double-ron-on-honba", EAGER_DOUBLE_RON_SEED).replay(
        Outcome({"rt": WireRoundResultType.EXHAUSTIVE_DRAW}, then=GAME_ENDS)
    )
    double_ron = {
        "rt": WireRoundResultType.DOUBLE_RON,
        "ls": 0,
        "wn": [{"ws": 1, "sch": {"0": -22, "1": 22}}, {"ws": 3, "sch": {"0": -22, "3": 22}}],
    }
    require_outcome(
        cut_after(game, event_type=WireEventType.ROUND_STARTED, occurrence=3),
        Outcome(double_ron, then=(WireEventType.ROUND_STARTED, {"n": 3, "h": 0})),
        name="double_ron_on_honba",
    )

    recording = cut_after(game, event_type=WireEventType.ROUND_END, occurrence=3)
    require_outcome(recording, Outcome({"rt": WireRoundResultType.TSUMO, "ws": 2}), name="double_ron_on_honba")
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
    "ron_riichi_discard.txt": ron_riichi_discard,
    "double_ron.txt": double_ron,
    "double_ron_head_bump.txt": double_ron_head_bump,
    "head_bump.txt": head_bump,
    "chankan_added.txt": chankan_added,
    "chankan_ai_replacement.txt": chankan_ai_replacement,
    "chankan_closed_kokushi.txt": chankan_closed_kokushi,
    "triple_ron.txt": triple_ron,
    "pao.txt": pao,
    "exhaustive_tenpai.txt": exhaustive_tenpai,
    "nagashi.txt": nagashi,
    "kyuushu.txt": kyuushu,
    "four_winds_riichi.txt": four_winds_riichi,
    "four_riichi.txt": four_riichi,
    "four_kans.txt": four_kans,
    "ai_replacements.txt": ai_replacements,
    "eager_game.txt": eager_game,
    "double_ron_on_honba.txt": double_ron_on_honba,
}
