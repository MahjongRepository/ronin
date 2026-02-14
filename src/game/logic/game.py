"""
Game initialization and progression for Mahjong.
"""

from game.logic.enums import GamePhase, RoundPhase, RoundResultType
from game.logic.round import DEAD_WALL_SIZE, FIRST_DORA_INDEX
from game.logic.settings import (
    EnchousenType,
    GameSettings,
    GameType,
    LeftoverRiichiBets,
    get_wind_thresholds,
    validate_settings,
)
from game.logic.state import (
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.state_utils import update_player
from game.logic.tiles import generate_wall, sort_tiles
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


def _goshashonyu_round(score: int, threshold: int) -> int:
    """
    Round a raw score using goshashonyu (五捨六入) rounding.

    Converts a raw score (relative to target) to points by dividing by 1000,
    rounding remainder <= threshold toward zero and remainder > threshold away from zero.
    """
    quotient = score // 1000
    remainder = abs(score) % 1000

    if score >= 0:
        if remainder > threshold:
            return quotient + 1
        return quotient

    # negative: python floor division already rounds toward negative infinity
    # -1900 // 1000 = -2, abs(-1900) % 1000 = 900
    # goshashonyu: -1.9 -> -2 (remainder 900 > 500, keep the floor)
    # -1500 // 1000 = -2, abs(-1500) % 1000 = 500
    # goshashonyu: -1.5 -> -1 (remainder 500 <= 500, round toward zero)
    if 0 < remainder <= threshold:
        return quotient + 1  # round toward zero (less negative)
    return quotient


def calculate_final_scores(
    raw_scores: list[tuple[int, int]],
    settings: GameSettings,
) -> list[tuple[int, int]]:
    """
    Calculate uma/oka-adjusted final scores from raw game scores.

    Input: list of (seat, raw_score) sorted by placement (1st to 4th).
    Output: list of (seat, final_score) in the same order.

    Steps:
    1. Subtract target score from each raw score
    2. Divide by 1000 with goshashonyu rounding
    3. Add oka bonus to 1st place
    4. Apply uma spread
    5. Adjust 1st place to ensure zero-sum
    """
    oka_total = ((settings.target_score - settings.starting_score) * 4) // 1000

    adjusted = []
    for i, (seat, raw_score) in enumerate(raw_scores):
        diff = raw_score - settings.target_score
        points = _goshashonyu_round(diff, settings.goshashonyu_threshold)

        # add oka to 1st place
        if i == 0:
            points += oka_total

        # apply uma
        points += settings.uma[i]

        adjusted.append((seat, points))

    # ensure zero-sum: adjust 1st place
    total = sum(score for _, score in adjusted)
    if total != 0:
        seat_0, score_0 = adjusted[0]
        adjusted[0] = (seat_0, score_0 - total)

    return adjusted


def init_game(
    seat_configs: list[SeatConfig],
    seed: float = 0.0,
    settings: GameSettings | None = None,
    wall: list[int] | None = None,
) -> MahjongGameState:
    """
    Initialize a new mahjong game with seat configurations.

    All players start with starting_score points (from settings).
    Dealer starts at seat 0, round wind starts at East.
    When wall is provided, use it instead of generating from seed.
    Returns a frozen MahjongGameState.
    """
    game_settings = settings or GameSettings()

    validate_settings(game_settings)

    # Create players
    players = tuple(
        MahjongPlayer(seat=i, name=config.name, score=game_settings.starting_score)
        for i, config in enumerate(seat_configs)
    )

    # Generate wall using seed, or use provided wall
    full_wall = wall if wall is not None else generate_wall(seed, 0)

    # Cut dead wall (14 tiles from end)
    dead_wall = tuple(full_wall[-DEAD_WALL_SIZE:])
    live_wall = tuple(full_wall[:-DEAD_WALL_SIZE])

    # Set first dora indicator (dead_wall[2])
    dora_indicators = (dead_wall[FIRST_DORA_INDEX],)

    # Deal tiles: each player draws 4 tiles x 3, then 1 more (total 13 each)
    wall_list = list(live_wall)
    dealer_seat = 0
    player_tiles: list[list[int]] = [[], [], [], []]

    # deal 4 tiles x 3 rounds
    for _ in range(3):
        for i in range(4):
            seat = (dealer_seat + i) % 4
            for _ in range(4):
                tile = wall_list.pop(0)
                player_tiles[seat].append(tile)

    # deal 1 more tile to each player
    for i in range(4):
        seat = (dealer_seat + i) % 4
        tile = wall_list.pop(0)
        player_tiles[seat].append(tile)

    # Sort each player's tiles and create updated players
    players = tuple(p.model_copy(update={"tiles": tuple(sort_tiles(player_tiles[p.seat]))}) for p in players)

    # Create round state
    round_state = MahjongRoundState(
        wall=tuple(wall_list),
        dead_wall=dead_wall,
        dora_indicators=dora_indicators,
        players=players,
        dealer_seat=dealer_seat,
        current_player_seat=dealer_seat,
        round_wind=0,  # East
        turn_count=0,
        all_discards=(),
        players_with_open_hands=(),
        pending_dora_count=0,
        phase=RoundPhase.PLAYING,
        pending_call_prompt=None,
    )

    # Create game state
    return MahjongGameState(
        round_state=round_state,
        round_number=0,
        unique_dealers=1,  # first dealer counts as 1
        honba_sticks=0,
        riichi_sticks=0,
        game_phase=GamePhase.IN_PROGRESS,
        seed=seed,
        settings=game_settings,
    )


def init_round(
    game_state: MahjongGameState,
) -> MahjongGameState:
    """
    Initialize a new round by generating wall, dealing tiles, and setting up dora.

    Returns new game state with the round initialized.
    """
    round_state = game_state.round_state

    # generate wall using seed + round_number
    wall = generate_wall(game_state.seed, game_state.round_number)

    # cut dead wall (14 tiles from end)
    dead_wall = tuple(wall[-DEAD_WALL_SIZE:])
    wall_list = list(wall[:-DEAD_WALL_SIZE])

    # Set first dora indicator (dead_wall[2])
    dora_indicators = (dead_wall[FIRST_DORA_INDEX],)

    # Reset player states and deal tiles
    dealer_seat = round_state.dealer_seat
    player_tiles: list[list[int]] = [[], [], [], []]

    # deal 4 tiles x 3 rounds
    for _ in range(3):
        for i in range(4):
            seat = (dealer_seat + i) % 4
            for _ in range(4):
                tile = wall_list.pop(0)
                player_tiles[seat].append(tile)

    # deal 1 more tile to each player
    for i in range(4):
        seat = (dealer_seat + i) % 4
        tile = wall_list.pop(0)
        player_tiles[seat].append(tile)

    # Create fresh player states with dealt tiles
    players = tuple(
        MahjongPlayer(
            seat=p.seat,
            name=p.name,
            tiles=tuple(sort_tiles(player_tiles[p.seat])),
            discards=(),
            melds=(),
            is_riichi=False,
            is_ippatsu=False,
            is_daburi=False,
            is_rinshan=False,
            kuikae_tiles=(),
            pao_seat=None,
            is_temporary_furiten=False,
            is_riichi_furiten=False,
            score=p.score,  # preserve score from previous round
        )
        for p in round_state.players
    )

    # Create new round state
    new_round_state = MahjongRoundState(
        wall=tuple(wall_list),
        dead_wall=dead_wall,
        dora_indicators=dora_indicators,
        players=players,
        dealer_seat=round_state.dealer_seat,
        current_player_seat=round_state.dealer_seat,
        round_wind=round_state.round_wind,
        turn_count=0,
        all_discards=(),
        players_with_open_hands=(),
        pending_dora_count=0,
        phase=RoundPhase.PLAYING,
        pending_call_prompt=None,
    )

    return game_state.model_copy(update={"round_state": new_round_state})


def _get_honba_and_rotation(  # noqa: PLR0911
    game_state: MahjongGameState,
    result: RoundResult,
) -> tuple[int, bool]:
    """Determine honba change and dealer rotation based on result type.

    Renchan behavior is controlled by three settings:
    - renchan_on_abortive_draw: if False, dealer rotates and honba resets on abortive draw
    - renchan_on_dealer_tenpai_draw: if False, dealer always rotates on exhaustive draw
    - renchan_on_dealer_win: if False, dealer rotates even when dealer wins
    """
    result_type = result.type
    dealer_seat = game_state.round_state.dealer_seat
    honba = game_state.honba_sticks
    settings = game_state.settings

    if result_type == RoundResultType.ABORTIVE_DRAW:
        if settings.renchan_on_abortive_draw:
            return honba + 1, False
        return 0, True

    if result_type == RoundResultType.EXHAUSTIVE_DRAW:
        if settings.renchan_on_dealer_tenpai_draw:
            is_draw = isinstance(result, ExhaustiveDrawResult)
            should_rotate = is_draw and dealer_seat not in result.tempai_seats
        else:
            should_rotate = True
        return honba + 1, should_rotate

    if result_type == RoundResultType.NAGASHI_MANGAN and isinstance(result, NagashiManganResult):
        if settings.renchan_on_dealer_tenpai_draw:
            return honba, dealer_seat not in result.tempai_seats
        return honba, True

    if result_type in (RoundResultType.TSUMO, RoundResultType.RON, RoundResultType.DOUBLE_RON):
        winner_seats = _get_winner_seats(result)
        if dealer_seat in winner_seats:
            if settings.renchan_on_dealer_win:
                return honba + 1, False
            return 0, True
        return 0, True

    raise AssertionError(f"unexpected round result type: {result_type}")  # pragma: no cover


def _get_winner_seats(result: RoundResult) -> list[int]:
    """Extract winner seats from a result."""
    if isinstance(result, (TsumoResult, RonResult)):
        return [result.winner_seat]
    if isinstance(result, DoubleRonResult):
        return [w.winner_seat for w in result.winners]
    raise AssertionError(f"unexpected result type in _get_winner_seats: {type(result)}")  # pragma: no cover


def _get_wind_for_unique_dealers(unique_dealers: int, settings: GameSettings) -> int:
    """Determine round wind based on unique dealers count."""
    east_max, south_max, _west_max = get_wind_thresholds(settings)
    if unique_dealers <= east_max:
        return 0  # East
    if unique_dealers <= south_max:
        return 1  # South
    return 2  # West


def process_round_end(
    game_state: MahjongGameState,
    result: RoundResult,
) -> MahjongGameState:
    """
    Process the end of a round and update game state.

    Handles dealer rotation and honba stick management based on round result type.
    """
    round_state = game_state.round_state
    dealer_seat = round_state.dealer_seat

    new_honba, should_rotate = _get_honba_and_rotation(game_state, result)

    # Compute dealer and wind changes
    new_dealer_seat = dealer_seat
    new_unique_dealers = game_state.unique_dealers
    new_round_wind = round_state.round_wind

    if should_rotate:
        new_dealer_seat = (dealer_seat + 1) % 4
        new_unique_dealers += 1
        new_round_wind = _get_wind_for_unique_dealers(new_unique_dealers, game_state.settings)

    # Create new round state with updated dealer and round wind
    new_round_state = round_state.model_copy(
        update={
            "dealer_seat": new_dealer_seat,
            "round_wind": new_round_wind,
        }
    )

    # Create new game state
    return game_state.model_copy(
        update={
            "round_state": new_round_state,
            "round_number": game_state.round_number + 1,
            "unique_dealers": new_unique_dealers,
            "honba_sticks": new_honba,
        }
    )


def check_game_end(game_state: MahjongGameState) -> bool:
    """
    Check if the game should end.

    Game ends when any of these conditions are met:
    - Tobi: any player's score drops below tobi_threshold (when tobi_enabled)
    - Primary wind complete and someone has winning_score_threshold+ points
      (East for tonpusen, South for hanchan)
    - If enchousen == NONE: game ends unconditionally after primary wind
    - Sudden death wind limit reached (South for tonpusen, West for hanchan)
    """
    round_state = game_state.round_state
    settings = game_state.settings

    # check tobi (player score below threshold)
    if settings.tobi_enabled and any(
        player.score < settings.tobi_threshold for player in round_state.players
    ):
        return True

    east_max, south_max, west_max = get_wind_thresholds(settings)
    has_winner = any(player.score >= settings.winning_score_threshold for player in round_state.players)

    if settings.game_type == GameType.TONPUSEN:
        # tonpusen: primary wind is East, sudden death extends into South
        primary_complete = game_state.unique_dealers > east_max
        sudden_death_limit = south_max
    else:
        # hanchan: primary wind is East + South, sudden death extends into West
        primary_complete = game_state.unique_dealers > south_max
        sudden_death_limit = west_max

    if primary_complete:
        if settings.enchousen == EnchousenType.NONE:
            return True
        if has_winner:
            return True

    # sudden death limit reached
    return game_state.unique_dealers > sudden_death_limit


def finalize_game(
    game_state: MahjongGameState,
    ai_player_seats: set[int] | None = None,
) -> tuple[MahjongGameState, GameEndResult]:
    """
    Finalize the game and determine winner.

    Winner is the player with highest score. Ties broken by seat order (lower seat wins).
    Winner receives remaining riichi_sticks * riichi_stick_value points.
    Final scores are adjusted with uma/oka.

    Returns (new_game_state, GameEndResult).
    """
    round_state = game_state.round_state

    # find winner: highest score, ties broken by lower seat
    winner_seat = 0
    highest_score = round_state.players[0].score
    for player in round_state.players:
        if player.score > highest_score:
            highest_score = player.score
            winner_seat = player.seat

    # handle remaining riichi sticks based on settings
    settings = game_state.settings
    new_round_state = round_state
    new_riichi_sticks = game_state.riichi_sticks
    if new_riichi_sticks > 0:
        if settings.leftover_riichi_bets == LeftoverRiichiBets.WINNER:
            riichi_bonus = new_riichi_sticks * settings.riichi_stick_value
            new_score = round_state.players[winner_seat].score + riichi_bonus
            new_round_state = update_player(new_round_state, winner_seat, score=new_score)
        # sticks are cleared regardless (WINNER: collected; LOST: disappear)
        new_riichi_sticks = 0

    # sort players by placement (descending score, ascending seat for ties)
    sorted_players = sorted(new_round_state.players, key=lambda p: (-p.score, p.seat))

    # calculate uma/oka-adjusted final scores
    raw_scores = [(p.seat, p.score) for p in sorted_players]
    final_scores = calculate_final_scores(raw_scores, settings)
    final_score_map = dict(final_scores)

    # build final standings with both raw and adjusted scores
    standings = [
        PlayerStanding(
            seat=player.seat,
            name=player.name,
            score=player.score,
            final_score=final_score_map[player.seat],
            is_ai_player=player.seat in (ai_player_seats or set()),
        )
        for player in sorted_players
    ]

    # Create new game state marked as finished
    new_game_state = game_state.model_copy(
        update={
            "round_state": new_round_state,
            "riichi_sticks": new_riichi_sticks,
            "game_phase": GamePhase.FINISHED,
        }
    )

    return new_game_state, GameEndResult(
        winner_seat=winner_seat,
        standings=standings,
    )
