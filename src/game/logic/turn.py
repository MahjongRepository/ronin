"""
Turn loop orchestration for Mahjong game.
"""

from typing import TYPE_CHECKING

from game.logic.abortive import (
    AbortiveDrawType,
    can_call_kyuushu_kyuuhai,
    check_four_kans,
    check_four_riichi,
    check_four_winds,
    check_triple_ron,
    process_abortive_draw,
)
from game.logic.melds import (
    call_added_kan,
    call_chi,
    call_closed_kan,
    call_open_kan,
    call_pon,
    can_call_chi,
    can_call_open_kan,
    can_call_pon,
    get_possible_added_kans,
    get_possible_closed_kans,
)
from game.logic.riichi import can_declare_riichi, declare_riichi
from game.logic.round import (
    advance_turn,
    check_exhaustive_draw,
    discard_tile,
    draw_tile,
    process_exhaustive_draw,
)
from game.logic.state import RoundPhase
from game.logic.tiles import tile_to_34, tile_to_string
from game.logic.win import (
    apply_double_ron_score,
    apply_ron_score,
    apply_tsumo_score,
    calculate_hand_value,
    can_call_ron,
    can_declare_tsumo,
    is_chankan_possible,
)

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState, MahjongRoundState


def process_draw_phase(round_state: MahjongRoundState, game_state: MahjongGameState) -> list[dict]:
    """
    Process the draw phase for the current player.

    Draws a tile and checks for available actions:
    - tsumo win
    - kyuushu kyuuhai (nine terminals abortive draw)
    - closed/added kan options

    Returns a list of events describing what happened and available options.
    """
    events = []
    current_seat = round_state.current_player_seat
    player = round_state.players[current_seat]

    # check for exhaustive draw before attempting to draw
    if check_exhaustive_draw(round_state):
        result = process_exhaustive_draw(round_state)
        round_state.phase = RoundPhase.FINISHED
        events.append({"type": "round_end", "result": result, "target": "all"})
        return events

    # draw a tile
    drawn_tile = draw_tile(round_state)
    if drawn_tile is None:
        # wall exhausted during draw (shouldn't happen if check above works)
        result = process_exhaustive_draw(round_state)
        round_state.phase = RoundPhase.FINISHED
        events.append({"type": "round_end", "result": result, "target": "all"})
        return events

    # notify player of drawn tile
    events.append(
        {
            "type": "draw",
            "seat": current_seat,
            "tile_id": drawn_tile,
            "tile": tile_to_string(drawn_tile),
            "target": f"seat_{current_seat}",
        }
    )

    # check for tsumo
    can_tsumo = can_declare_tsumo(player, round_state)

    # check for kyuushu kyuuhai
    can_kyuushu = can_call_kyuushu_kyuuhai(player, round_state)

    # check for kan options
    wall_count = len(round_state.wall)
    closed_kans = get_possible_closed_kans(player, wall_count)
    added_kans = get_possible_added_kans(player, wall_count)

    # build available actions for the player
    available_actions = get_available_actions(round_state, game_state, current_seat)
    available_actions["can_tsumo"] = can_tsumo
    available_actions["can_kyuushu"] = can_kyuushu
    available_actions["closed_kans"] = closed_kans
    available_actions["added_kans"] = added_kans

    events.append(
        {
            "type": "turn",
            "current_seat": current_seat,
            "available_actions": available_actions,
            "wall_count": len(round_state.wall),
            "target": f"seat_{current_seat}",
        }
    )

    return events


def process_discard_phase(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    tile_id: int,
    *,
    is_riichi: bool = False,
) -> list[dict]:
    """
    Process the discard phase after a player discards a tile.

    Steps:
    1. If is_riichi: mark riichi step 1 (declared but not finalized)
    2. Validate and execute discard
    3. Check for four winds abortive draw
    4. Check for ron from other players
       - If 3 players can ron: triple ron abortive draw
       - If 1-2 players can ron: process win(s)
    5. If no ron and is_riichi: finalize riichi step 2
    6. Check for meld calls with priority: kan > pon > chi
    7. If no calls, advance turn

    Returns list of events describing what happened.
    """
    events = []
    current_seat = round_state.current_player_seat
    player = round_state.players[current_seat]

    # step 1: mark riichi if declaring
    riichi_pending = False
    if is_riichi:
        if not can_declare_riichi(player, round_state):
            raise ValueError("cannot declare riichi: conditions not met")
        riichi_pending = True

    # step 2: execute discard
    discard = discard_tile(round_state, current_seat, tile_id, is_riichi=is_riichi)

    events.append(
        {
            "type": "discard",
            "seat": current_seat,
            "tile_id": tile_id,
            "tile": tile_to_string(tile_id),
            "is_tsumogiri": discard.is_tsumogiri,
            "is_riichi": is_riichi,
            "target": "all",
        }
    )

    # step 3: check for four winds abortive draw
    if check_four_winds(round_state):
        result = process_abortive_draw(game_state, AbortiveDrawType.FOUR_WINDS)
        round_state.phase = RoundPhase.FINISHED
        events.append({"type": "round_end", "result": result, "target": "all"})
        return events

    # step 4: check for ron from other players
    ron_callers = _find_ron_callers(round_state, tile_id, current_seat)

    if check_triple_ron(ron_callers):
        # triple ron is abortive draw
        result = process_abortive_draw(game_state, AbortiveDrawType.TRIPLE_RON)
        round_state.phase = RoundPhase.FINISHED
        events.append({"type": "round_end", "result": result, "target": "all"})
        return events

    if ron_callers:
        # ron opportunities exist - create call prompt
        # in actual game, this would wait for player decisions
        # here we return events indicating ron is available
        events.append(
            {
                "type": "call_prompt",
                "call_type": "ron",
                "tile_id": tile_id,
                "from_seat": current_seat,
                "callers": ron_callers,
                "target": "all",
            }
        )
        return events

    # step 5: finalize riichi if no ron
    if riichi_pending:
        declare_riichi(player, game_state)
        events.append(
            {
                "type": "riichi_declared",
                "seat": current_seat,
                "target": "all",
            }
        )

        # check for four riichi abortive draw
        if check_four_riichi(round_state):
            result = process_abortive_draw(game_state, AbortiveDrawType.FOUR_RIICHI)
            round_state.phase = RoundPhase.FINISHED
            events.append({"type": "round_end", "result": result, "target": "all"})
            return events

    # step 6: check for meld calls (priority: kan > pon > chi)
    meld_calls = _find_meld_callers(round_state, tile_id, current_seat)

    if meld_calls:
        events.append(
            {
                "type": "call_prompt",
                "call_type": "meld",
                "tile_id": tile_id,
                "from_seat": current_seat,
                "callers": meld_calls,
                "target": "all",
            }
        )
        return events

    # step 7: no calls, advance turn
    advance_turn(round_state)

    return events


class MeldCallContext:
    """Context for processing a meld call."""

    def __init__(
        self,
        round_state: MahjongRoundState,
        game_state: MahjongGameState,
        caller_seat: int,
        tile_id: int,
        sequence_tiles: tuple[int, int] | None = None,
    ) -> None:
        self.round_state = round_state
        self.game_state = game_state
        self.caller_seat = caller_seat
        self.tile_id = tile_id
        self.sequence_tiles = sequence_tiles
        self.discarder_seat = round_state.current_player_seat
        self.events: list[dict] = []

    def check_four_kans_abort(self) -> bool:
        """Check for four kans abortive draw. Returns True if game should end."""
        if check_four_kans(self.round_state):
            result = process_abortive_draw(self.game_state, AbortiveDrawType.FOUR_KANS)
            self.round_state.phase = RoundPhase.FINISHED
            self.events.append({"type": "round_end", "result": result, "target": "all"})
            return True
        return False


def _process_pon_call(ctx: MeldCallContext) -> None:
    """Process pon call."""
    meld = call_pon(ctx.round_state, ctx.caller_seat, ctx.discarder_seat, ctx.tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    ctx.events.append(
        {
            "type": "meld",
            "meld_type": "pon",
            "caller_seat": ctx.caller_seat,
            "from_seat": ctx.discarder_seat,
            "tile_ids": tile_ids,
            "tiles": [tile_to_string(t) for t in tile_ids],
            "target": "all",
        }
    )


def _process_chi_call(ctx: MeldCallContext) -> None:
    """Process chi call."""
    if ctx.sequence_tiles is None:
        raise ValueError("chi call requires sequence_tiles")
    meld = call_chi(ctx.round_state, ctx.caller_seat, ctx.discarder_seat, ctx.tile_id, ctx.sequence_tiles)
    tile_ids = list(meld.tiles) if meld.tiles else []
    ctx.events.append(
        {
            "type": "meld",
            "meld_type": "chi",
            "caller_seat": ctx.caller_seat,
            "from_seat": ctx.discarder_seat,
            "tile_ids": tile_ids,
            "tiles": [tile_to_string(t) for t in tile_ids],
            "target": "all",
        }
    )


def _process_open_kan_call(ctx: MeldCallContext) -> bool:
    """Process open kan call. Returns True if round ended."""
    meld = call_open_kan(ctx.round_state, ctx.caller_seat, ctx.discarder_seat, ctx.tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    ctx.events.append(
        {
            "type": "meld",
            "meld_type": "kan",
            "kan_type": "open",
            "caller_seat": ctx.caller_seat,
            "from_seat": ctx.discarder_seat,
            "tile_ids": tile_ids,
            "tiles": [tile_to_string(t) for t in tile_ids],
            "target": "all",
        }
    )
    return ctx.check_four_kans_abort()


def _process_closed_kan_call(ctx: MeldCallContext) -> bool:
    """Process closed kan call. Returns True if round ended."""
    meld = call_closed_kan(ctx.round_state, ctx.caller_seat, ctx.tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    ctx.events.append(
        {
            "type": "meld",
            "meld_type": "kan",
            "kan_type": "closed",
            "caller_seat": ctx.caller_seat,
            "tile_ids": tile_ids,
            "tiles": [tile_to_string(t) for t in tile_ids],
            "target": "all",
        }
    )
    return ctx.check_four_kans_abort()


def _process_added_kan_call(ctx: MeldCallContext) -> bool:
    """Process added kan call. Returns True if round ended or waiting for chankan."""
    chankan_seats = is_chankan_possible(ctx.round_state, ctx.caller_seat, ctx.tile_id)
    if chankan_seats:
        ctx.events.append(
            {
                "type": "call_prompt",
                "call_type": "chankan",
                "tile_id": ctx.tile_id,
                "from_seat": ctx.caller_seat,
                "callers": chankan_seats,
                "target": "all",
            }
        )
        return True

    meld = call_added_kan(ctx.round_state, ctx.caller_seat, ctx.tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    ctx.events.append(
        {
            "type": "meld",
            "meld_type": "kan",
            "kan_type": "added",
            "caller_seat": ctx.caller_seat,
            "tile_ids": tile_ids,
            "tiles": [tile_to_string(t) for t in tile_ids],
            "target": "all",
        }
    )
    return ctx.check_four_kans_abort()


def process_meld_call(  # noqa: PLR0913
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    call_type: str,
    tile_id: int,
    *,
    sequence_tiles: tuple[int, int] | None = None,
) -> list[dict]:
    """
    Process a meld call (pon, chi, open kan, closed kan, added kan).

    For pon/chi/open kan: the tile_id is the discarded tile being called.
    For closed kan: tile_id is one of the 4 tiles to kan.
    For added kan: tile_id is the 4th tile to add to existing pon.

    Returns events describing the meld and any follow-up (chankan check for added kan).
    """
    ctx = MeldCallContext(round_state, game_state, caller_seat, tile_id, sequence_tiles)

    if call_type == "pon":
        _process_pon_call(ctx)
    elif call_type == "chi":
        _process_chi_call(ctx)
    elif call_type == "open_kan":
        if _process_open_kan_call(ctx):
            return ctx.events
    elif call_type == "closed_kan":
        if _process_closed_kan_call(ctx):
            return ctx.events
    elif call_type == "added_kan":
        if _process_added_kan_call(ctx):
            return ctx.events
    else:
        raise ValueError(f"unknown call_type: {call_type}")

    return ctx.events


def process_ron_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    ron_callers: list[int],
    tile_id: int,
    discarder_seat: int,
) -> list[dict]:
    """
    Process ron call(s) from one or more players.

    Returns events for the ron result.
    """
    events = []

    if len(ron_callers) == 1:
        # single ron
        winner_seat = ron_callers[0]
        winner = round_state.players[winner_seat]

        # temporarily add the tile to calculate hand value
        winner.tiles.append(tile_id)
        hand_result = calculate_hand_value(winner, round_state, tile_id, is_tsumo=False)
        winner.tiles.remove(tile_id)

        if hand_result.error:
            raise ValueError(f"ron calculation error: {hand_result.error}")

        result = apply_ron_score(game_state, winner_seat, discarder_seat, hand_result)
        round_state.phase = RoundPhase.FINISHED
        events.append({"type": "round_end", "result": result, "target": "all"})

    elif len(ron_callers) == 2:
        # double ron
        winners = []
        for winner_seat in ron_callers:
            winner = round_state.players[winner_seat]
            winner.tiles.append(tile_id)
            hand_result = calculate_hand_value(winner, round_state, tile_id, is_tsumo=False)
            winner.tiles.remove(tile_id)

            if hand_result.error:
                raise ValueError(f"ron calculation error for seat {winner_seat}: {hand_result.error}")

            winners.append((winner_seat, hand_result))

        result = apply_double_ron_score(game_state, winners, discarder_seat)
        round_state.phase = RoundPhase.FINISHED
        events.append({"type": "round_end", "result": result, "target": "all"})

    return events


def process_tsumo_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    winner_seat: int,
) -> list[dict]:
    """
    Process tsumo declaration from a player.

    Returns events for the tsumo result.
    """
    events = []
    winner = round_state.players[winner_seat]

    if not can_declare_tsumo(winner, round_state):
        raise ValueError("cannot declare tsumo: conditions not met")

    # the win tile is the last tile in hand (just drawn)
    win_tile = winner.tiles[-1]
    hand_result = calculate_hand_value(winner, round_state, win_tile, is_tsumo=True)

    if hand_result.error:
        raise ValueError(f"tsumo calculation error: {hand_result.error}")

    result = apply_tsumo_score(game_state, winner_seat, hand_result)
    round_state.phase = RoundPhase.FINISHED
    events.append({"type": "round_end", "result": result, "target": "all"})

    return events


def get_available_actions(
    round_state: MahjongRoundState,
    _game_state: MahjongGameState,
    seat: int,
) -> dict:
    """
    Return available actions for a player at their turn.

    Includes:
    - discardable tiles
    - riichi option (if eligible)
    - tsumo option (if hand is winning)
    - kan options (closed and added)
    """
    player = round_state.players[seat]
    wall_count = len(round_state.wall)

    # all tiles in hand can be discarded (unless in riichi)
    # in riichi, must discard the drawn tile (tsumogiri)
    discard_tiles = ([player.tiles[-1]] if player.tiles else []) if player.is_riichi else list(player.tiles)

    # check riichi eligibility
    riichi_available = can_declare_riichi(player, round_state)

    # check tsumo
    tsumo_available = can_declare_tsumo(player, round_state)

    # check kan options
    closed_kans = get_possible_closed_kans(player, wall_count)
    added_kans = get_possible_added_kans(player, wall_count)

    return {
        "discard_tiles": discard_tiles,
        "can_riichi": riichi_available,
        "can_tsumo": tsumo_available,
        "closed_kans": closed_kans,
        "added_kans": added_kans,
    }


def _find_ron_callers(round_state: MahjongRoundState, tile_id: int, discarder_seat: int) -> list[int]:
    """
    Find all players who can call ron on the discarded tile.

    Returns list of seat numbers sorted by priority (counter-clockwise from discarder).
    """
    ron_callers = []

    for seat in range(4):
        if seat == discarder_seat:
            continue

        player = round_state.players[seat]
        if can_call_ron(player, tile_id, round_state):
            ron_callers.append(seat)

    # sort by priority: counter-clockwise from discarder (closer = higher priority)
    def distance_from_discarder(s: int) -> int:
        return (s - discarder_seat) % 4

    ron_callers.sort(key=distance_from_discarder)

    return ron_callers


def _find_meld_callers(
    round_state: MahjongRoundState,
    tile_id: int,
    discarder_seat: int,
) -> list[dict]:
    """
    Find all players who can call a meld on the discarded tile.

    Returns list of meld options sorted by priority (kan > pon > chi).
    Each entry includes: seat, call_type, and options (for chi).
    """
    meld_calls = []
    wall_count = len(round_state.wall)
    tile_34 = tile_to_34(tile_id)

    for seat in range(4):
        if seat == discarder_seat:
            continue

        player = round_state.players[seat]

        # check open kan
        if can_call_open_kan(player, tile_id, wall_count):
            meld_calls.append(
                {
                    "seat": seat,
                    "call_type": "open_kan",
                    "tile_34": tile_34,
                    "priority": 0,  # highest priority
                }
            )

        # check pon
        if can_call_pon(player, tile_id):
            meld_calls.append(
                {
                    "seat": seat,
                    "call_type": "pon",
                    "tile_34": tile_34,
                    "priority": 1,
                }
            )

        # check chi (only from kamicha)
        chi_options = can_call_chi(player, tile_id, discarder_seat, seat)
        if chi_options:
            meld_calls.append(
                {
                    "seat": seat,
                    "call_type": "chi",
                    "tile_34": tile_34,
                    "options": chi_options,
                    "priority": 2,  # lowest priority
                }
            )

    # sort by priority
    meld_calls.sort(key=lambda x: x["priority"])

    return meld_calls
