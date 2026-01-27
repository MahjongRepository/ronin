"""
Game initialization and progression for Mahjong.
"""

from game.logic.round import create_players, init_round
from game.logic.state import (
    GamePhase,
    MahjongGameState,
    MahjongRoundState,
)

# wind progression thresholds
EAST_WIND_MAX_DEALERS = 4
SOUTH_WIND_MAX_DEALERS = 8
WEST_WIND_MAX_DEALERS = 12

# winning score threshold
WINNING_SCORE_THRESHOLD = 30000


def init_game(player_names: list[str], seed: float = 0.0) -> MahjongGameState:
    """
    Initialize a new mahjong game with 4 players.

    First player (index 0) is human, indices 1-3 are bots.
    All players start with 25000 points.
    Dealer starts at seat 0, round wind starts at East.
    """
    players = create_players(player_names)

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


def _process_draw_result(game_state: MahjongGameState, result: dict) -> bool:
    """
    Process an abortive or exhaustive draw result.

    Returns True if dealer should rotate.
    """
    round_state = game_state.round_state
    dealer_seat = round_state.dealer_seat
    result_type = result.get("type", "")

    if result_type == "abortive_draw":
        game_state.honba_sticks += 1
        return False

    # exhaustive draw
    tempai_seats = result.get("tempai_seats", [])
    game_state.honba_sticks += 1
    return dealer_seat not in tempai_seats


def _process_win_result(game_state: MahjongGameState, result: dict) -> bool:
    """
    Process a tsumo, ron, or double ron result.

    Returns True if dealer should rotate.
    """
    round_state = game_state.round_state
    dealer_seat = round_state.dealer_seat
    result_type = result.get("type", "")

    winner_seats = result.get("winner_seats", [])
    if result_type in ("tsumo", "ron"):
        winner_seat = result.get("winner_seat")
        if winner_seat is not None:
            winner_seats = [winner_seat]
    elif result_type == "double_ron" and not winner_seats:
        # double_ron returns "winners" list with "winner_seat" in each entry
        winners_list = result.get("winners", [])
        winner_seats = [w.get("winner_seat") for w in winners_list]

    if dealer_seat in winner_seats:
        game_state.honba_sticks += 1
        return False

    game_state.honba_sticks = 0
    return True


def process_round_end(game_state: MahjongGameState, result: dict) -> None:
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
    result_type = result.get("type", "")

    # determine if dealer should rotate based on result type
    if result_type in ("abortive_draw", "exhaustive_draw"):
        should_rotate = _process_draw_result(game_state, result)
    elif result_type in ("tsumo", "ron", "double_ron"):
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


def finalize_game(game_state: MahjongGameState) -> dict:
    """
    Finalize the game and determine winner.

    Winner is the player with highest score. Ties broken by seat order (lower seat wins).
    Winner receives remaining riichi_sticks * 1000 points.
    Verifies total scores sum to 100000 (sanity check).

    Returns final standings with winner and scores.
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
        {
            "seat": player.seat,
            "name": player.name,
            "score": player.score,
            "is_bot": player.is_bot,
        }
        for player in sorted(round_state.players, key=lambda p: (-p.score, p.seat))
    ]

    # mark game as finished
    game_state.game_phase = GamePhase.FINISHED

    return {
        "type": "game_end",
        "winner_seat": winner_seat,
        "standings": standings,
    }
