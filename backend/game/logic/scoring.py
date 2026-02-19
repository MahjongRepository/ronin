"""
Scoring calculation for Mahjong game.

Handles hand value calculation and score application for wins (tsumo, ron, double ron).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig

from game.logic.meld_compact import frozen_meld_to_compact
from game.logic.meld_wrapper import frozen_melds_to_melds
from game.logic.settings import GameSettings, RenhouValue, build_optional_rules
from game.logic.state import seat_to_wind
from game.logic.state_utils import update_player
from game.logic.tiles import WINDS_34, hand_to_34_array
from game.logic.types import (
    DoubleRonResult,
    DoubleRonWinner,
    HandResultInfo,
    NagashiManganResult,
    RonResult,
    TenpaiHand,
    TsumoResult,
    YakuInfo,
)
from game.logic.wall import collect_ura_dora_indicators as _wall_collect_ura_dora
from game.logic.wall import tiles_remaining
from game.logic.win import (
    all_player_tiles,
    is_chiihou,
    is_haitei,
    is_houtei,
    is_renhou,
    is_tenhou,
)

if TYPE_CHECKING:
    from game.logic.state import (
        MahjongGameState,
        MahjongPlayer,
        MahjongRoundState,
    )

logger = logging.getLogger(__name__)


@dataclass
class HandResult:
    """
    Result of hand value calculation.
    """

    han: int = 0
    fu: int = 0
    cost_main: int = 0  # cost paid by dealer (tsumo) or loser (ron)
    cost_additional: int = 0  # cost paid by non-dealers (tsumo only)
    yaku: list[YakuInfo] = field(default_factory=list)
    error: str | None = None  # error message if calculation failed


@dataclass(frozen=True)
class ScoringContext:
    """Group common scoring parameters: player, round/game state, settings, and win flags."""

    player: MahjongPlayer
    round_state: MahjongRoundState
    settings: GameSettings
    is_tsumo: bool
    is_chankan: bool = False


def _build_hand_config(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    settings: GameSettings,
    *,
    is_tsumo: bool,
    is_chankan: bool = False,
) -> HandConfig:
    """Build HandConfig with all relevant flags for scoring."""
    haitei_flag = is_tsumo and is_haitei(round_state)
    houtei_flag = not is_tsumo and is_houtei(round_state)
    tenhou_flag = is_tsumo and is_tenhou(player, round_state)
    chiihou_flag = is_tsumo and is_chiihou(player, round_state)
    renhou_flag = not is_tsumo and settings.renhou_value != RenhouValue.NONE and is_renhou(player, round_state)

    return HandConfig(
        is_tsumo=is_tsumo,
        is_riichi=player.is_riichi,
        is_ippatsu=player.is_ippatsu and settings.has_ippatsu,
        is_daburu_riichi=player.is_daburi,
        is_rinshan=player.is_rinshan,
        is_chankan=is_chankan,
        is_haitei=haitei_flag,
        is_houtei=houtei_flag,
        is_tenhou=tenhou_flag,
        is_chiihou=chiihou_flag,
        is_renhou=renhou_flag,
        player_wind=seat_to_wind(player.seat, round_state.dealer_seat),
        round_wind=WINDS_34[round_state.round_wind],
        options=build_optional_rules(settings),
    )


def collect_ura_dora_indicators(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    settings: GameSettings,
) -> list[int] | None:
    """
    Collect ura dora indicator tile IDs for a riichi winner.

    Return None when player is not riichi or ura dora is disabled.
    Return the list of ura dora indicator tile IDs otherwise.
    """
    if not settings.has_uradora or not player.is_riichi:
        return None

    indicators = _wall_collect_ura_dora(
        round_state.wall,
        include_kan_ura=settings.has_kan_uradora,
    )
    return indicators or None


def _collect_dora_indicators(
    round_state: MahjongRoundState,
    settings: GameSettings,
) -> list[int]:
    """Collect omote (face-up) dora indicators for scoring."""
    if settings.has_omote_dora:
        return list(round_state.wall.dora_indicators) if round_state.wall.dora_indicators else []
    return []


def _evaluate_hand(
    ctx: ScoringContext,
    tiles: list[int],
    win_tile: int,
) -> HandResult:
    """Build scoring config, collect dora, run hand calculator, and return result."""
    config = _build_hand_config(
        ctx.player,
        ctx.round_state,
        ctx.settings,
        is_tsumo=ctx.is_tsumo,
        is_chankan=ctx.is_chankan,
    )
    dora_indicators = _collect_dora_indicators(ctx.round_state, ctx.settings)
    ura_dora_indicators = collect_ura_dora_indicators(ctx.player, ctx.round_state, ctx.settings)

    melds = frozen_melds_to_melds(ctx.player.melds)
    result = HandCalculator.estimate_hand_value(
        tiles=tiles,
        win_tile=win_tile,
        melds=melds,
        dora_indicators=dora_indicators,
        config=config,
        ura_dora_indicators=ura_dora_indicators,
    )

    if result.error:
        tile_counts_34 = hand_to_34_array(tiles)
        discard_ids = [discard.tile_id for discard in ctx.player.discards]
        logger.error(
            f"hand calculation error: {result.error} "
            f"(seat={ctx.player.seat} name={ctx.player.name} "
            f"tiles={tiles} tiles_34={tile_counts_34} tiles_count={len(tiles)} "
            f"discards={discard_ids} discards_count={len(discard_ids)} "
            f"round_wind={ctx.round_state.round_wind} dealer_seat={ctx.round_state.dealer_seat} "
            f"phase={ctx.round_state.phase.value} wall_count={tiles_remaining(ctx.round_state.wall)} "
            f"pending_dora_count={ctx.round_state.wall.pending_dora_count} ",
        )
        return HandResult(error=result.error)

    yaku_list: list[YakuInfo] = []
    if result.yaku:
        for y in result.yaku:
            han = y.han_open if result.is_open_hand and y.han_open > 0 else y.han_closed
            yaku_list.append(YakuInfo(yaku_id=y.yaku_id, han=han))
    return HandResult(
        han=result.han or 0,
        fu=result.fu or 0,
        cost_main=result.cost["main"] if result.cost else 0,
        cost_additional=result.cost["additional"] if result.cost else 0,
        yaku=yaku_list,
    )


def calculate_hand_value(ctx: ScoringContext, win_tile: int) -> HandResult:
    """
    Calculate the value of a winning hand using the mahjong library's HandCalculator.

    Build HandConfig with all relevant flags and OptionalRules for scoring.
    Return a HandResult with han, fu, cost breakdown, and yaku list.
    """
    tiles = all_player_tiles(ctx.player)
    return _evaluate_hand(ctx, tiles, win_tile)


def calculate_hand_value_with_tiles(
    ctx: ScoringContext,
    tiles: list[int],
    win_tile: int,
) -> HandResult:
    """
    Calculate the value of a winning hand using explicit tiles list.

    Accept tiles directly instead of reading from player.tiles. Use this for
    ron calculations where the win tile needs to be included in the tiles list.
    """
    return _evaluate_hand(ctx, tiles, win_tile)


def _current_scores(game_state: MahjongGameState) -> dict[int, int]:
    """Extract current scores from game state (after riichi deductions, before payment)."""
    return {p.seat: p.score for p in game_state.round_state.players}


def _apply_score_changes(
    game_state: MahjongGameState,
    score_changes: dict[int, int],
    *,
    clear_riichi: bool = True,
) -> tuple[MahjongRoundState, MahjongGameState]:
    """Apply score changes to round state and optionally clear riichi sticks."""
    new_round_state = game_state.round_state
    for seat, change in score_changes.items():
        player = new_round_state.players[seat]
        new_round_state = update_player(new_round_state, seat, score=player.score + change)

    updates: dict[str, object] = {"round_state": new_round_state}
    if clear_riichi:
        updates["riichi_sticks"] = 0

    new_game_state = game_state.model_copy(update=updates)
    return new_round_state, new_game_state


def _tsumo_payment_for_seat(
    seat: int,
    *,
    is_dealer_win: bool,
    dealer_seat: int,
    hand_result: HandResult,
    honba_bonus_per_loser: int,
) -> int:
    """
    Calculate the tsumo payment amount a given seat owes.
    """
    if is_dealer_win or seat == dealer_seat:
        return hand_result.cost_main + honba_bonus_per_loser
    return hand_result.cost_additional + honba_bonus_per_loser


def apply_tsumo_score(
    game_state: MahjongGameState,
    winner_seat: int,
    hand_result: HandResult,
) -> tuple[MahjongRoundState, MahjongGameState, TsumoResult]:
    """
    Apply score changes for a tsumo win.

    Returns (new_round_state, new_game_state, result).

    Payment structure (normal):
    - If winner is dealer: each non-dealer pays main_cost
    - If winner is non-dealer: dealer pays main_cost, others pay additional_cost
    - Winner also gets: riichi_sticks * 1000 + honba * 300
    - Each loser pays: +honba/3 bonus (300 total = 100 per loser)

    Payment structure (pao / liability):
    - The liable player pays the full tsumo amount alone
    - Other players pay nothing
    """
    round_state = game_state.round_state
    settings = game_state.settings
    scores = _current_scores(game_state)
    winner = round_state.players[winner_seat]
    is_dealer_win = winner_seat == round_state.dealer_seat
    honba_bonus_per_loser = game_state.honba_sticks * settings.honba_tsumo_bonus_per_loser

    score_changes: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}

    if winner.pao_seat is not None:
        # pao tsumo: liable player pays the full amount
        total_payment = sum(
            _tsumo_payment_for_seat(
                s,
                is_dealer_win=is_dealer_win,
                dealer_seat=round_state.dealer_seat,
                hand_result=hand_result,
                honba_bonus_per_loser=honba_bonus_per_loser,
            )
            for s in range(4)
            if s != winner_seat
        )
        score_changes[winner.pao_seat] = -total_payment
        score_changes[winner_seat] = total_payment
    else:
        # normal tsumo scoring
        total_payment = 0
        for seat in range(4):
            if seat == winner_seat:
                continue
            payment = _tsumo_payment_for_seat(
                seat,
                is_dealer_win=is_dealer_win,
                dealer_seat=round_state.dealer_seat,
                hand_result=hand_result,
                honba_bonus_per_loser=honba_bonus_per_loser,
            )
            score_changes[seat] = -payment
            total_payment += payment
        score_changes[winner_seat] = total_payment

    # winner receives riichi sticks
    riichi_bonus = game_state.riichi_sticks * settings.riichi_stick_value
    score_changes[winner_seat] += riichi_bonus

    new_round_state, new_game_state = _apply_score_changes(game_state, score_changes)

    return (
        new_round_state,
        new_game_state,
        TsumoResult(
            winner_seat=winner_seat,
            hand_result=HandResultInfo(
                han=hand_result.han,
                fu=hand_result.fu,
                yaku=hand_result.yaku,
            ),
            scores=scores,
            score_changes=score_changes,
            riichi_sticks_collected=riichi_bonus // settings.riichi_stick_value,
            closed_tiles=list(winner.tiles),
            melds=[frozen_meld_to_compact(m) for m in winner.melds],
            win_tile=winner.tiles[-1],
            pao_seat=winner.pao_seat,
            ura_dora_indicators=collect_ura_dora_indicators(winner, round_state, settings),
        ),
    )


def apply_ron_score(
    game_state: MahjongGameState,
    winner_seat: int,
    loser_seat: int,
    hand_result: HandResult,
    winning_tile: int,
) -> tuple[MahjongRoundState, MahjongGameState, RonResult]:
    """
    Apply score changes for a ron win.

    Returns (new_round_state, new_game_state, result).

    Payment structure (normal):
    - Loser pays: main_cost + honba * 300
    - Winner gets: main_cost + riichi_sticks * 1000 + honba * 300

    Payment structure (pao / liability, pao_seat != loser_seat):
    - Loser and pao player split the payment 50/50
    - Winner receives the full amount

    If pao_seat == loser_seat, normal ron applies (pao player pays full as they would anyway).
    """
    round_state = game_state.round_state
    settings = game_state.settings
    scores = _current_scores(game_state)
    winner = round_state.players[winner_seat]

    # honba bonus from loser
    honba_bonus = game_state.honba_sticks * settings.honba_ron_bonus

    total_payment = hand_result.cost_main + honba_bonus
    riichi_bonus = game_state.riichi_sticks * settings.riichi_stick_value

    score_changes: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}

    if winner.pao_seat is not None and winner.pao_seat != loser_seat:
        # pao ron with different pao player: split 50/50
        # assign rounding remainder to the pao (liable) player
        half = total_payment // 2
        pao_half = total_payment - half
        score_changes[loser_seat] = -half
        score_changes[winner.pao_seat] -= pao_half
        score_changes[winner_seat] = total_payment
    else:
        # normal ron (including pao_seat == loser_seat case)
        score_changes[loser_seat] = -total_payment
        score_changes[winner_seat] = total_payment

    # winner receives riichi sticks
    score_changes[winner_seat] += riichi_bonus

    new_round_state, new_game_state = _apply_score_changes(game_state, score_changes)

    return (
        new_round_state,
        new_game_state,
        RonResult(
            winner_seat=winner_seat,
            loser_seat=loser_seat,
            winning_tile=winning_tile,
            hand_result=HandResultInfo(
                han=hand_result.han,
                fu=hand_result.fu,
                yaku=hand_result.yaku,
            ),
            scores=scores,
            score_changes=score_changes,
            riichi_sticks_collected=riichi_bonus // settings.riichi_stick_value,
            closed_tiles=list(winner.tiles),
            melds=[frozen_meld_to_compact(m) for m in winner.melds],
            pao_seat=winner.pao_seat,
            ura_dora_indicators=collect_ura_dora_indicators(winner, round_state, settings),
        ),
    )


def apply_double_ron_score(
    game_state: MahjongGameState,
    winners: list[tuple[int, HandResult]],  # list of (seat, hand_result)
    loser_seat: int,
    winning_tile: int,
) -> tuple[MahjongRoundState, MahjongGameState, DoubleRonResult]:
    """
    Apply score changes for a double ron.

    Returns (new_round_state, new_game_state, result).

    Payment structure:
    - Loser pays each winner separately: main_cost + honba * 300
    - Riichi sticks go to winner closest to loser's right (counter-clockwise)
    - Each winner's pao is evaluated independently (same logic as single ron)
    """
    round_state = game_state.round_state
    settings = game_state.settings
    scores = _current_scores(game_state)

    score_changes: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}
    honba_bonus = game_state.honba_sticks * settings.honba_ron_bonus
    riichi_bonus = game_state.riichi_sticks * settings.riichi_stick_value

    # determine who gets riichi sticks: winner closest to loser's right (counter-clockwise)
    winner_seats = {w[0] for w in winners}
    riichi_receiver: int | None = None
    for offset in range(1, 4):
        check_seat = (loser_seat + offset) % 4
        if check_seat in winner_seats:
            riichi_receiver = check_seat
            break
    if riichi_receiver is None:
        raise ValueError("No riichi receiver found in double ron")

    winner_results = []

    for winner_seat, hand_result in winners:
        winner = round_state.players[winner_seat]
        payment = hand_result.cost_main + honba_bonus

        if winner.pao_seat is not None and winner.pao_seat != loser_seat:
            # pao ron with different pao player: split 50/50
            # assign rounding remainder to the pao (liable) player
            half = payment // 2
            pao_half = payment - half
            score_changes[loser_seat] -= half
            score_changes[winner.pao_seat] -= pao_half
        else:
            # normal ron (including pao_seat == loser_seat case)
            score_changes[loser_seat] -= payment

        winner_total = payment
        if winner_seat == riichi_receiver:
            winner_total += riichi_bonus

        score_changes[winner_seat] += winner_total

        winner_results.append(
            DoubleRonWinner(
                winner_seat=winner_seat,
                hand_result=HandResultInfo(
                    han=hand_result.han,
                    fu=hand_result.fu,
                    yaku=hand_result.yaku,
                ),
                riichi_sticks_collected=(
                    riichi_bonus // settings.riichi_stick_value if winner_seat == riichi_receiver else 0
                ),
                closed_tiles=list(winner.tiles),
                melds=[frozen_meld_to_compact(m) for m in winner.melds],
                pao_seat=winner.pao_seat,
                ura_dora_indicators=collect_ura_dora_indicators(winner, round_state, settings),
            ),
        )

    new_round_state, new_game_state = _apply_score_changes(game_state, score_changes)

    return (
        new_round_state,
        new_game_state,
        DoubleRonResult(
            loser_seat=loser_seat,
            winning_tile=winning_tile,
            winners=winner_results,
            scores=scores,
            score_changes=score_changes,
        ),
    )


def apply_nagashi_mangan_score(
    game_state: MahjongGameState,
    qualifying_seats: list[int],
    tempai_seats: list[int],
    noten_seats: list[int],
    tenpai_hands: list[TenpaiHand],
) -> tuple[MahjongRoundState, MahjongGameState, NagashiManganResult]:
    """
    Apply nagashi mangan scoring.

    Returns (new_round_state, new_game_state, result).

    Each qualifying player receives mangan tsumo payment:
    - Dealer: 4000 from each non-dealer (12000 total)
    - Non-dealer: 4000 from dealer + 2000 from each non-dealer (8000 total)
    """
    round_state = game_state.round_state
    settings = game_state.settings
    scores = _current_scores(game_state)
    score_changes: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}

    for winner_seat in qualifying_seats:
        is_dealer = winner_seat == round_state.dealer_seat
        for seat in range(4):
            if seat == winner_seat:
                continue
            payment = (
                settings.nagashi_mangan_dealer_payment
                if is_dealer or seat == round_state.dealer_seat
                else settings.nagashi_mangan_non_dealer_payment
            )
            score_changes[seat] -= payment
            score_changes[winner_seat] += payment

    new_round_state, new_game_state = _apply_score_changes(game_state, score_changes, clear_riichi=False)

    return (
        new_round_state,
        new_game_state,
        NagashiManganResult(
            qualifying_seats=qualifying_seats,
            tempai_seats=tempai_seats,
            noten_seats=noten_seats,
            tenpai_hands=tenpai_hands,
            scores=scores,
            score_changes=score_changes,
        ),
    )
