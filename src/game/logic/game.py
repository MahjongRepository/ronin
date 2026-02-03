"""
Game initialization and progression for Mahjong.
"""

from game.logic.enums import RoundResultType
from game.logic.round import create_players, init_round
from game.logic.state import (
    GamePhase,
    MahjongGameState,
    MahjongRoundState,
)
from game.logic.types import (
    DoubleRonResult,
    ExhaustiveDrawResult,
    GameEndResult,
    NagashiManganResult,
    PlayerStanding,
    RonResult,
    RoundResult,
    SeatConfig,
    TsumoResult,
)

# wind progression thresholds
EAST_WIND_MAX_DEALERS = 4
SOUTH_WIND_MAX_DEALERS = 8
WEST_WIND_MAX_DEALERS = 12

# winning score threshold
WINNING_SCORE_THRESHOLD = 30000

# uma/oka scoring constants
STARTING_SCORE = 25000
TARGET_SCORE = 30000
UMA_SPREAD = [20, 10, -10, -20]  # 1st, 2nd, 3rd, 4th
GOSHASHONYU_THRESHOLD = 500  # goshashonyu: remainder <= 500 rounds toward zero


def init_game(seat_configs: list[SeatConfig], seed: float = 0.0) -> MahjongGameState:
    """
    Initialize a new mahjong game with seat configurations.

    All players start with 25000 points.
    Dealer starts at seat 0, round wind starts at East.
    """
    players = create_players(seat_configs)

    round_state = MahjongRoundState(
        players=players,
        dealer_seat=0,
        round_wind=0,  # East
    )

    game_state = MahjongGameState(
        round_state=round_state,
        round_number=0,
        unique_dealers=1,  # first dealer counts as 1
        honba_sticks=0,
        riichi_sticks=0,
        game_phase=GamePhase.IN_PROGRESS,
        seed=seed,
    )

    # initialize the first round
    init_round(game_state)

    return game_state


def _process_draw_result(game_state: MahjongGameState, result: RoundResult) -> bool:
    """
    Process an abortive or exhaustive draw result.

    Returns True if dealer should rotate.
    """
    dealer_seat = game_state.round_state.dealer_seat

    if result.type == RoundResultType.ABORTIVE_DRAW:
        game_state.honba_sticks += 1
        return False

    # exhaustive draw
    game_state.honba_sticks += 1
    if isinstance(result, ExhaustiveDrawResult):
        return dealer_seat not in result.tempai_seats
    return False


def _process_win_result(game_state: MahjongGameState, result: RoundResult) -> bool:
    """
    Process a tsumo, ron, or double ron result.

    Returns True if dealer should rotate.
    """
    dealer_seat = game_state.round_state.dealer_seat

    winner_seats: list[int] = []
    if isinstance(result, (TsumoResult, RonResult)):
        winner_seats = [result.winner_seat]
    elif isinstance(result, DoubleRonResult):
        winner_seats = [w.winner_seat for w in result.winners]

    if dealer_seat in winner_seats:
        game_state.honba_sticks += 1
        return False

    game_state.honba_sticks = 0
    return True


def process_round_end(game_state: MahjongGameState, result: RoundResult) -> None:
    """
    Process the end of a round and update game state.

    Handles dealer rotation and honba stick management based on round result type:
    - abortive draw: increment honba, don't rotate dealer
    - dealer won (or one of multiple winners): increment honba, don't rotate
    - exhaustive draw with dealer tempai: increment honba, don't rotate
    - exhaustive draw with dealer noten: increment honba, rotate dealer
    - nagashi mangan: no honba change, dealer rotates if noten
    - dealer lost (ron/tsumo, dealer not winner): reset honba to 0, rotate dealer

    Updates unique_dealers when dealer changes, which drives wind progression.
    """
    round_state = game_state.round_state
    result_type = result.type

    # determine if dealer should rotate based on result type
    if result_type in (RoundResultType.ABORTIVE_DRAW, RoundResultType.EXHAUSTIVE_DRAW):
        should_rotate = _process_draw_result(game_state, result)
    elif result_type == RoundResultType.NAGASHI_MANGAN and isinstance(result, NagashiManganResult):
        # nagashi mangan: no honba increment, dealer rotates if noten
        should_rotate = round_state.dealer_seat not in result.tempai_seats
    elif result_type in (RoundResultType.TSUMO, RoundResultType.RON, RoundResultType.DOUBLE_RON):
        should_rotate = _process_win_result(game_state, result)
    else:
        should_rotate = False

    # rotate dealer if needed
    if should_rotate:
        round_state.dealer_seat = (round_state.dealer_seat + 1) % 4
        game_state.unique_dealers += 1

        # wind progression: unique_dealers 1-4 = East, 5-8 = South, 9-12 = West
        if game_state.unique_dealers <= EAST_WIND_MAX_DEALERS:
            round_state.round_wind = 0  # East
        elif game_state.unique_dealers <= SOUTH_WIND_MAX_DEALERS:
            round_state.round_wind = 1  # South
        else:
            round_state.round_wind = 2  # West

    # increment round number
    game_state.round_number += 1


def check_game_end(game_state: MahjongGameState) -> bool:
    """
    Check if the game should end.

    Game ends when any of these conditions are met:
    - Any player has negative points (below 0)
    - South wind complete (unique_dealers > 8) and someone has 30000+ points
    - West wind complete (unique_dealers > 12)
    """
    round_state = game_state.round_state

    # check if any player has negative points
    if any(player.score < 0 for player in round_state.players):
        return True

    # check if South wind complete and someone has 30000+
    south_complete = game_state.unique_dealers > SOUTH_WIND_MAX_DEALERS
    has_winner = any(player.score >= WINNING_SCORE_THRESHOLD for player in round_state.players)
    if south_complete and has_winner:
        return True

    # check if West wind complete
    return game_state.unique_dealers > WEST_WIND_MAX_DEALERS


def _goshashonyu_round(score: int) -> int:
    """
    Round a raw score using goshashonyu (五捨六入) rounding.

    Converts a raw score (relative to target) to points by dividing by 1000,
    rounding remainder <= 500 toward zero and remainder > 500 away from zero.
    """
    quotient = score // 1000
    remainder = abs(score) % 1000

    if score >= 0:
        if remainder > GOSHASHONYU_THRESHOLD:
            return quotient + 1
        return quotient

    # negative: python floor division already rounds toward negative infinity
    # -1900 // 1000 = -2, abs(-1900) % 1000 = 900
    # goshashonyu: -1.9 -> -2 (remainder 900 > 500, keep the floor)
    # -1500 // 1000 = -2, abs(-1500) % 1000 = 500
    # goshashonyu: -1.5 -> -1 (remainder 500 <= 500, round toward zero)
    if 0 < remainder <= GOSHASHONYU_THRESHOLD:
        return quotient + 1  # round toward zero (less negative)
    return quotient


def calculate_final_scores(raw_scores: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """
    Calculate uma/oka-adjusted final scores from raw game scores.

    Input: list of (seat, raw_score) sorted by placement (1st to 4th).
    Output: list of (seat, final_score) in the same order.

    Steps:
    1. Subtract target score (30000) from each raw score
    2. Divide by 1000 with goshashonyu rounding
    3. Add oka bonus (20) to 1st place
    4. Apply uma spread (20, 10, -10, -20)
    5. Adjust 1st place to ensure zero-sum
    """
    oka_total = ((TARGET_SCORE - STARTING_SCORE) * 4) // 1000  # 20 points

    adjusted = []
    for i, (seat, raw_score) in enumerate(raw_scores):
        diff = raw_score - TARGET_SCORE
        points = _goshashonyu_round(diff)

        # add oka to 1st place
        if i == 0:
            points += oka_total

        # apply uma
        points += UMA_SPREAD[i]

        adjusted.append((seat, points))

    # ensure zero-sum: adjust 1st place
    total = sum(score for _, score in adjusted)
    if total != 0:
        seat_0, score_0 = adjusted[0]
        adjusted[0] = (seat_0, score_0 - total)

    return adjusted


def finalize_game(game_state: MahjongGameState, bot_seats: set[int] | None = None) -> GameEndResult:
    """
    Finalize the game and determine winner.

    Winner is the player with highest score. Ties broken by seat order (lower seat wins).
    Winner receives remaining riichi_sticks * 1000 points.
    Final scores are adjusted with uma/oka.
    """
    round_state = game_state.round_state

    # find winner: highest score, ties broken by lower seat
    winner_seat = 0
    highest_score = round_state.players[0].score
    for player in round_state.players:
        if player.score > highest_score:
            highest_score = player.score
            winner_seat = player.seat

    # winner gets remaining riichi sticks
    if game_state.riichi_sticks > 0:
        round_state.players[winner_seat].score += game_state.riichi_sticks * 1000
        game_state.riichi_sticks = 0

    # sort players by placement (descending score, ascending seat for ties)
    sorted_players = sorted(round_state.players, key=lambda p: (-p.score, p.seat))

    # calculate uma/oka-adjusted final scores
    raw_scores = [(p.seat, p.score) for p in sorted_players]
    final_scores = calculate_final_scores(raw_scores)
    final_score_map = dict(final_scores)

    # build final standings with both raw and adjusted scores
    standings = [
        PlayerStanding(
            seat=player.seat,
            name=player.name,
            score=player.score,
            final_score=final_score_map[player.seat],
            is_bot=player.seat in (bot_seats or set()),
        )
        for player in sorted_players
    ]

    # mark game as finished
    game_state.game_phase = GamePhase.FINISHED

    return GameEndResult(
        winner_seat=winner_seat,
        standings=standings,
    )
