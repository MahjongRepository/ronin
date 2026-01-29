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
    - dealer lost (ron/tsumo, dealer not winner): reset honba to 0, rotate dealer

    Updates unique_dealers when dealer changes, which drives wind progression.
    """
    round_state = game_state.round_state
    result_type = result.type

    # determine if dealer should rotate based on result type
    if result_type in (RoundResultType.ABORTIVE_DRAW, RoundResultType.EXHAUSTIVE_DRAW):
        should_rotate = _process_draw_result(game_state, result)
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


def finalize_game(game_state: MahjongGameState) -> GameEndResult:
    """
    Finalize the game and determine winner.

    Winner is the player with highest score. Ties broken by seat order (lower seat wins).
    Winner receives remaining riichi_sticks * 1000 points.
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

    # build final standings
    standings = [
        PlayerStanding(
            seat=player.seat,
            name=player.name,
            score=player.score,
            is_bot=player.is_bot,
        )
        for player in sorted(round_state.players, key=lambda p: (-p.score, p.seat))
    ]

    # mark game as finished
    game_state.game_phase = GamePhase.FINISHED

    return GameEndResult(
        winner_seat=winner_seat,
        standings=standings,
    )
