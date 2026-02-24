"""
Turn loop orchestration for Mahjong game.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from game.logic.abortive import (
    AbortiveDrawType,
    can_call_kyuushu_kyuuhai,
    check_four_kans,
    check_four_riichi,
    check_four_winds,
    check_triple_ron,
    process_abortive_draw,
)
from game.logic.actions import get_available_actions
from game.logic.enums import (
    FALLBACK_MELD_PRIORITY,
    MELD_CALL_PRIORITY,
    CallType,
    MeldCallType,
    MeldViewType,
    PlayerAction,
    RoundPhase,
)
from game.logic.events import (
    CallPromptEvent,
    DiscardEvent,
    DoraRevealedEvent,
    DrawEvent,
    GameEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
)
from game.logic.exceptions import (
    InvalidActionError,
    InvalidMeldError,
    InvalidRiichiError,
    InvalidWinError,
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
    resolve_added_kan_tile,
    validate_closed_kan,
)
from game.logic.riichi import can_declare_riichi, declare_riichi
from game.logic.round import (
    check_exhaustive_draw,
    discard_tile,
    draw_tile,
    is_tempai,
    process_exhaustive_draw,
    reveal_pending_dora,
)
from game.logic.scoring import (
    ScoringContext,
    apply_double_ron_score,
    apply_ron_score,
    apply_tsumo_score,
    calculate_hand_value,
    calculate_hand_value_with_tiles,
)
from game.logic.settings import NUM_PLAYERS
from game.logic.state import (
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    PendingCallPrompt,
)
from game.logic.state_utils import (
    advance_turn,
    update_player,
)
from game.logic.tiles import tile_to_34
from game.logic.types import AvailableActionItem, MeldCaller, MeldCallInput, RonCallInput
from game.logic.win import (
    all_tiles_from_hand_and_melds,
    can_call_ron,
    can_declare_tsumo,
    get_waiting_tiles,
    is_chankan_possible,
    is_kokushi_chankan_possible,
)

if TYPE_CHECKING:
    from game.logic.settings import GameSettings

logger = structlog.get_logger()


def _maybe_emit_dora_event(
    old_dora_count: int,
    new_round_state: MahjongRoundState,
    events: list[GameEvent],
) -> None:
    """Append DoraRevealedEvents for each new dora indicator revealed."""
    events.extend(
        DoraRevealedEvent(tile_id=indicator) for indicator in new_round_state.wall.dora_indicators[old_dora_count:]
    )


def emit_deferred_dora_events(
    round_state: MahjongRoundState,
) -> tuple[MahjongRoundState, list[GameEvent]]:
    """
    Reveal deferred dora indicators (from open/added kan) and emit events.

    Called after a discard passes the ron check. Under our rules,
    open/added kan dora is revealed only after the replacement discard
    is accepted (not ron'd).

    Returns (new_round_state, events).
    """
    new_state, revealed = reveal_pending_dora(round_state)

    events: list[GameEvent] = [
        DoraRevealedEvent(
            tile_id=dora_tile_id,
        )
        for dora_tile_id in revealed
    ]

    return new_state, events


def process_draw_phase(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Process the draw phase for the current player.

    Draws a tile and checks for available actions:
    - tsumo win
    - kyuushu kyuuhai (nine terminals abortive draw)
    - closed/added kan options

    Returns (new_round_state, new_game_state, events).
    """
    events: list[GameEvent] = []
    current_seat = round_state.current_player_seat

    # check for exhaustive draw before attempting to draw
    if check_exhaustive_draw(round_state):
        logger.debug("exhaustive draw")
        new_round_state, new_game_state, result = process_exhaustive_draw(game_state)
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(RoundEndEvent(result=result, target="all"))
        return new_round_state, new_game_state, events

    # draw a tile
    new_round_state, drawn_tile = draw_tile(round_state)
    if drawn_tile is None:  # pragma: no cover
        raise AssertionError("drawn_tile is None after exhaustive draw check passed")

    logger.debug("tile drawn", tile_id=drawn_tile)

    # update game state with new round state
    new_game_state = game_state.model_copy(update={"round_state": new_round_state})

    # build available actions for the player (already includes tsumo, riichi, kan options)
    available_actions = get_available_actions(new_round_state, new_game_state, current_seat)

    # check for kyuushu kyuuhai and add to actions if available
    settings = game_state.settings
    player = new_round_state.players[current_seat]
    if settings.has_kyuushu_kyuuhai and can_call_kyuushu_kyuuhai(player, new_round_state, settings):
        available_actions.append(AvailableActionItem(action=PlayerAction.KYUUSHU))

    events.append(
        DrawEvent(
            seat=current_seat,
            tile_id=drawn_tile,
            available_actions=available_actions,
            target=f"seat_{current_seat}",
        ),
    )

    return new_round_state, new_game_state, events


def _check_riichi_furiten(
    round_state: MahjongRoundState,
    tile_id: int,
    discarder_seat: int,
    ron_callers: list[int],
) -> MahjongRoundState:
    """
    Set riichi furiten for riichi players whose winning tile just passed.

    A riichi player who is waiting on the discarded tile but did not (or could not)
    call ron becomes permanently furiten for the rest of the hand.

    Returns new round state with updated furiten flags.
    """
    tile_34 = tile_to_34(tile_id)
    new_state = round_state

    for seat in range(NUM_PLAYERS):
        if seat == discarder_seat:
            continue
        player = new_state.players[seat]
        if not player.is_riichi:
            continue
        if seat in ron_callers:
            # they can call ron; riichi furiten only applies if they later pass
            continue
        waiting = get_waiting_tiles(player)
        if tile_34 in waiting:
            new_state = update_player(new_state, seat, is_riichi_furiten=True)

    return new_state


def _find_meld_callers(
    round_state: MahjongRoundState,
    tile_id: int,
    discarder_seat: int,
    settings: GameSettings,
) -> list[MeldCaller]:
    """
    Find all players who can call a meld on the discarded tile.

    Returns list of MeldCaller options sorted by priority (kan > pon > chi).
    Each entry includes: seat, call_type, and options (for chi).

    Last discard restriction: when the live wall is empty, no meld calls are
    allowed (only ron). This applies to the final discard of a hand.
    """
    if not round_state.wall.live_tiles:
        return []

    meld_calls: list[MeldCaller] = []

    for seat in range(NUM_PLAYERS):
        if seat == discarder_seat:
            continue

        player = round_state.players[seat]

        # check open kan
        if can_call_open_kan(player, tile_id, round_state, settings):
            meld_calls.append(
                MeldCaller(
                    seat=seat,
                    call_type=MeldCallType.OPEN_KAN,
                ),
            )

        # check pon
        if can_call_pon(player, tile_id):
            meld_calls.append(
                MeldCaller(
                    seat=seat,
                    call_type=MeldCallType.PON,
                ),
            )

        # check chi (only from kamicha)
        chi_options = can_call_chi(player, tile_id, discarder_seat, seat)
        if chi_options:
            meld_calls.append(
                MeldCaller(
                    seat=seat,
                    call_type=MeldCallType.CHI,
                    options=tuple(chi_options),
                ),
            )

    # sort by priority: kan > pon > chi
    meld_calls.sort(key=lambda x: MELD_CALL_PRIORITY.get(x.call_type, FALLBACK_MELD_PRIORITY))

    return meld_calls


def _validate_riichi_discard(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    tile_id: int,
    settings: GameSettings,
) -> None:
    """Validate riichi declaration and that the discard keeps hand in tenpai.

    Raises InvalidRiichiError if conditions are not met.
    """
    if not can_declare_riichi(player, round_state, settings):
        logger.error("cannot declare riichi: conditions not met", seat=player.seat)
        raise InvalidRiichiError("cannot declare riichi: conditions not met")

    removed = False
    simulated: list[int] = []
    for t in player.tiles:
        if t == tile_id and not removed:
            removed = True
            continue
        simulated.append(t)
    if not removed:
        raise InvalidRiichiError(f"tile {tile_id} not in hand")
    if not is_tempai(tuple(simulated), player.melds):
        raise InvalidRiichiError(f"hand is not tenpai after discarding tile {tile_id}")


def _check_abortive_draw(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    draw_type: AbortiveDrawType,
    events: list[GameEvent],
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Produce abortive draw result and mark round finished."""
    logger.debug("abortive draw", draw_type=draw_type.value)
    result = process_abortive_draw(game_state, draw_type)
    new_round = round_state.model_copy(update={"phase": RoundPhase.FINISHED})
    new_game = game_state.model_copy(update={"round_state": new_round})
    events.append(RoundEndEvent(result=result, target="all"))
    return new_round, new_game, events


def _build_discard_prompt(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    tile_id: int,
    ron_callers: list[int],
    meld_calls: list[MeldCaller],
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Create a unified DISCARD call prompt for all callers."""
    discarder_seat = round_state.current_player_seat
    callers: list[int | MeldCaller] = list(ron_callers) + list(meld_calls)
    ron_caller_set = set(ron_callers)
    all_caller_seats = ron_caller_set | {c.seat for c in meld_calls}
    prompt = PendingCallPrompt(
        call_type=CallType.DISCARD,
        tile_id=tile_id,
        from_seat=discarder_seat,
        pending_seats=frozenset(all_caller_seats),
        callers=tuple(callers),
    )
    new_round = round_state.model_copy(update={"pending_call_prompt": prompt})
    new_game = game_state.model_copy(update={"round_state": new_round})
    events: list[GameEvent] = [
        CallPromptEvent(
            call_type=CallType.DISCARD,
            tile_id=tile_id,
            from_seat=discarder_seat,
            callers=callers,
            target="all",
        ),
    ]
    return new_round, new_game, events


def _finalize_no_callers(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    current_seat: int,
    *,
    riichi_pending: bool,
    events: list[GameEvent],
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Handle the no-callers path: reveal deferred dora, finalize riichi, advance turn."""
    settings = game_state.settings
    new_round, dora_events = emit_deferred_dora_events(round_state)
    events.extend(dora_events)
    new_game = game_state.model_copy(update={"round_state": new_round})

    if riichi_pending:
        new_round, new_game = declare_riichi(new_round, new_game, current_seat, settings)
        events.append(RiichiDeclaredEvent(seat=current_seat, target="all"))

        if settings.has_suucha_riichi and check_four_riichi(new_round, settings):
            return _check_abortive_draw(new_round, new_game, AbortiveDrawType.FOUR_RIICHI, events)

    new_round = advance_turn(new_round)
    new_game = new_game.model_copy(update={"round_state": new_round})
    return new_round, new_game, events


def process_discard_phase(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    tile_id: int,
    *,
    is_riichi: bool = False,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Process the discard phase after a player discards a tile.

    Steps:
    1. If is_riichi: validate riichi conditions
    2. Validate and execute discard
    3. Check for four winds abortive draw
    4. Check for ron callers; check triple ron abortive draw
    5. Check for meld callers (ron-dominant policy)
    6. If any callers: create unified DISCARD prompt
    7. No callers: reveal deferred dora, finalize riichi, advance turn

    Returns (new_round_state, new_game_state, events).
    """
    events: list[GameEvent] = []
    current_seat = round_state.current_player_seat
    player = round_state.players[current_seat]
    settings = game_state.settings

    riichi_pending = False
    if is_riichi:
        _validate_riichi_discard(player, round_state, tile_id, settings)
        riichi_pending = True

    new_round_state, discard = discard_tile(round_state, current_seat, tile_id, is_riichi=is_riichi)
    new_game_state = game_state.model_copy(update={"round_state": new_round_state})

    events.append(
        DiscardEvent(
            seat=current_seat,
            tile_id=tile_id,
            is_tsumogiri=discard.is_tsumogiri,
            is_riichi=is_riichi,
        ),
    )

    logger.debug("tile discarded", tile_id=tile_id, is_tsumogiri=discard.is_tsumogiri, is_riichi=is_riichi)

    # check for four winds abortive draw
    if settings.has_suufon_renda and check_four_winds(new_round_state, settings):
        return _check_abortive_draw(new_round_state, new_game_state, AbortiveDrawType.FOUR_WINDS, events)

    # find ron callers and apply riichi furiten
    ron_callers = _find_ron_callers(new_round_state, tile_id, current_seat, settings)
    new_round_state = _check_riichi_furiten(new_round_state, tile_id, current_seat, ron_callers)
    new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})

    if settings.has_triple_ron_abort and check_triple_ron(ron_callers, settings.triple_ron_count):
        return _check_abortive_draw(new_round_state, new_game_state, AbortiveDrawType.TRIPLE_RON, events)

    # find meld callers (ron-dominant: seats with ron don't get meld options)
    ron_caller_set = set(ron_callers)
    all_meld_calls = _find_meld_callers(new_round_state, tile_id, current_seat, settings)
    meld_calls = [c for c in all_meld_calls if c.seat not in ron_caller_set]

    if ron_callers or meld_calls:
        new_round, new_game, prompt_events = _build_discard_prompt(
            new_round_state,
            new_game_state,
            tile_id,
            ron_callers,
            meld_calls,
        )
        return new_round, new_game, events + prompt_events

    return _finalize_no_callers(
        new_round_state,
        new_game_state,
        current_seat,
        riichi_pending=riichi_pending,
        events=events,
    )


def _find_ron_callers(
    round_state: MahjongRoundState,
    tile_id: int,
    discarder_seat: int,
    settings: GameSettings,
) -> list[int]:
    """
    Find all players who can call ron on the discarded tile.

    Returns list of seat numbers sorted by priority (counter-clockwise from discarder).
    """
    ron_callers = []

    for seat in range(NUM_PLAYERS):
        if seat == discarder_seat:
            continue

        player = round_state.players[seat]
        if can_call_ron(player, tile_id, round_state, settings):
            ron_callers.append(seat)

    # sort by priority: counter-clockwise from discarder (closer = higher priority)
    def distance_from_discarder(s: int) -> int:
        return (s - discarder_seat) % NUM_PLAYERS

    ron_callers.sort(key=distance_from_discarder)

    return ron_callers


def process_ron_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    ron_input: RonCallInput,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Process ron call(s) from one or more players.

    Uses local tile copies for hand calculation.

    Returns (new_round_state, new_game_state, events).
    """
    events: list[GameEvent] = []
    settings = game_state.settings
    ron_callers = ron_input.ron_callers
    tile_id = ron_input.tile_id
    discarder_seat = ron_input.discarder_seat
    is_chankan = ron_input.is_chankan

    if len(ron_callers) == 1:
        # single ron
        winner_seat = ron_callers[0]
        winner = round_state.players[winner_seat]

        # build complete tile list with the ron tile added (closed hand + melds + win tile)
        tiles_with_win = all_tiles_from_hand_and_melds([*list(winner.tiles), tile_id], winner.melds)

        # calculate hand value using explicit tiles list
        ctx = ScoringContext(
            player=winner,
            round_state=round_state,
            settings=settings,
            is_tsumo=False,
            is_chankan=is_chankan,
        )
        hand_result = calculate_hand_value_with_tiles(ctx, tiles_with_win, tile_id)

        if hand_result.error:
            logger.error("ron calculation error", winner_seat=winner_seat, error=hand_result.error)
            raise InvalidWinError(f"ron calculation error: {hand_result.error}")

        new_round_state, new_game_state, result = apply_ron_score(
            game_state,
            winner_seat,
            discarder_seat,
            hand_result,
            tile_id,
        )
        logger.debug(
            "ron declared",
            winner_seat=winner_seat,
            loser_seat=discarder_seat,
            tile_id=tile_id,
            han=hand_result.han,
            fu=hand_result.fu,
            cost=hand_result.cost_main,
        )
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(RoundEndEvent(result=result, target="all"))

    elif len(ron_callers) == settings.double_ron_count:
        # double ron
        winners = []
        for winner_seat in ron_callers:
            winner = round_state.players[winner_seat]

            # build complete tile list with the ron tile added (closed hand + melds + win tile)
            tiles_with_win = all_tiles_from_hand_and_melds([*list(winner.tiles), tile_id], winner.melds)

            # calculate hand value using explicit tiles list
            ctx = ScoringContext(
                player=winner,
                round_state=round_state,
                settings=settings,
                is_tsumo=False,
                is_chankan=is_chankan,
            )
            hand_result = calculate_hand_value_with_tiles(ctx, tiles_with_win, tile_id)

            if hand_result.error:
                logger.error("ron calculation error", winner_seat=winner_seat, error=hand_result.error)
                raise InvalidWinError(f"ron calculation error for seat {winner_seat}: {hand_result.error}")

            winners.append((winner_seat, hand_result))

        new_round_state, new_game_state, result = apply_double_ron_score(
            game_state,
            winners,
            discarder_seat,
            tile_id,
        )
        logger.debug(
            "double ron declared",
            winner_seats=[s for s, _ in winners],
            loser_seat=discarder_seat,
            tile_id=tile_id,
        )
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(RoundEndEvent(result=result, target="all"))
    else:  # pragma: no cover
        raise AssertionError("process_ron_call called with no valid winner count")

    return new_round_state, new_game_state, events


def process_tsumo_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    winner_seat: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Process tsumo declaration from a player.

    Returns (new_round_state, new_game_state, events).
    """
    events: list[GameEvent] = []
    settings = game_state.settings
    winner = round_state.players[winner_seat]

    if not can_declare_tsumo(winner, round_state, settings):
        logger.error("cannot declare tsumo: conditions not met", seat=winner_seat)
        raise InvalidWinError("cannot declare tsumo: conditions not met")

    # clear pending dora: tsumo win (e.g. rinshan kaihou after open/added kan)
    # scores before the deferred dora indicator would have been revealed
    new_wall = round_state.wall.model_copy(update={"pending_dora_count": 0})
    new_round_state = round_state.model_copy(update={"wall": new_wall})

    # the win tile is the last tile in hand (just drawn)
    win_tile = winner.tiles[-1]
    ctx = ScoringContext(player=winner, round_state=new_round_state, settings=settings, is_tsumo=True)
    hand_result = calculate_hand_value(ctx, win_tile)

    if hand_result.error:
        logger.error("tsumo calculation error", winner_seat=winner_seat, error=hand_result.error)
        raise InvalidWinError(f"tsumo calculation error: {hand_result.error}")

    # apply score changes
    new_game_state = game_state.model_copy(update={"round_state": new_round_state})
    new_round_state, new_game_state, result = apply_tsumo_score(new_game_state, winner_seat, hand_result)
    logger.debug(
        "tsumo declared",
        winner_seat=winner_seat,
        tile_id=win_tile,
        han=hand_result.han,
        fu=hand_result.fu,
        cost=hand_result.cost_main,
    )
    new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
    new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
    events.append(RoundEndEvent(result=result, target="all"))

    return new_round_state, new_game_state, events


def _process_pon_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    discarder_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Handle a pon meld call."""
    logger.debug("pon called", caller_seat=caller_seat, from_seat=discarder_seat, tile_id=tile_id)
    new_round_state, meld = call_pon(round_state, caller_seat, discarder_seat, tile_id, game_state.settings)
    tile_ids = list(meld.tiles)
    events: list[GameEvent] = [
        MeldEvent(
            meld_type=MeldViewType.PON,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            from_seat=discarder_seat,
            called_tile_id=tile_id,
        ),
    ]
    return new_round_state, game_state.model_copy(update={"round_state": new_round_state}), events


def _process_chi_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
    sequence_tiles: tuple[int, int],
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Handle a chi meld call."""
    logger.debug("chi called", caller_seat=caller_seat, tile_id=tile_id, sequence_tiles=sequence_tiles)
    discarder_seat = round_state.current_player_seat
    new_round_state, meld = call_chi(
        round_state,
        caller_seat,
        discarder_seat,
        tile_id,
        sequence_tiles,
        game_state.settings,
    )
    tile_ids = list(meld.tiles)
    events: list[GameEvent] = [
        MeldEvent(
            meld_type=MeldViewType.CHI,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            from_seat=discarder_seat,
            called_tile_id=tile_id,
        ),
    ]
    return new_round_state, game_state.model_copy(update={"round_state": new_round_state}), events


def _check_four_kans_abort(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    events: list[GameEvent],
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent], bool]:
    """Check for four kans abortive draw. Return (round, game, events, aborted)."""
    settings = game_state.settings
    if settings.has_suukaikan and check_four_kans(round_state, settings):
        new_game_state = game_state.model_copy(update={"round_state": round_state})
        result = process_abortive_draw(new_game_state, AbortiveDrawType.FOUR_KANS)
        new_round_state = round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(RoundEndEvent(result=result, target="all"))
        return new_round_state, new_game_state, events, True
    new_game_state = game_state.model_copy(update={"round_state": round_state})
    return round_state, new_game_state, events, False


def _process_open_kan_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    discarder_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Handle an open kan meld call."""
    logger.debug("open kan called", caller_seat=caller_seat, from_seat=discarder_seat, tile_id=tile_id)
    old_dora_count = len(round_state.wall.dora_indicators)
    new_round_state, meld = call_open_kan(
        round_state,
        caller_seat,
        discarder_seat,
        tile_id,
        game_state.settings,
    )
    tile_ids = list(meld.tiles)
    events: list[GameEvent] = [
        MeldEvent(
            meld_type=MeldViewType.OPEN_KAN,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            from_seat=discarder_seat,
            called_tile_id=tile_id,
        ),
    ]
    _maybe_emit_dora_event(old_dora_count, new_round_state, events)
    new_round_state, new_game_state, events, _aborted = _check_four_kans_abort(
        new_round_state,
        game_state,
        events,
    )
    return new_round_state, new_game_state, events


def _process_closed_kan_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Handle a closed kan meld call."""
    logger.debug("closed kan called", caller_seat=caller_seat, tile_id=tile_id)

    # validate the closed kan is legal before checking for kokushi chankan,
    # so a forged payload cannot trigger a chankan window for an illegal kan
    validate_closed_kan(round_state, caller_seat, tile_id, game_state.settings)

    # kokushi musou may rob a closed kan; check before executing
    kokushi_seats = is_kokushi_chankan_possible(round_state, caller_seat, tile_id)
    if kokushi_seats:
        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=tile_id,
            from_seat=caller_seat,
            pending_seats=frozenset(kokushi_seats),
            callers=tuple(kokushi_seats),
        )
        new_round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        new_game_state = game_state.model_copy(update={"round_state": new_round_state})
        chankan_callers: list[int | MeldCaller] = list(kokushi_seats)
        events: list[GameEvent] = [
            CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=tile_id,
                from_seat=caller_seat,
                callers=chankan_callers,
                target="all",
            ),
        ]
        return new_round_state, new_game_state, events

    old_dora_count = len(round_state.wall.dora_indicators)
    new_round_state, meld = call_closed_kan(round_state, caller_seat, tile_id, game_state.settings)
    tile_ids = list(meld.tiles)
    events = [
        MeldEvent(
            meld_type=MeldViewType.CLOSED_KAN,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
        ),
    ]
    _maybe_emit_dora_event(old_dora_count, new_round_state, events)
    new_round_state, new_game_state, events, _aborted = _check_four_kans_abort(
        new_round_state,
        game_state,
        events,
    )
    return new_round_state, new_game_state, events


def _process_added_kan_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Handle an added kan meld call."""
    logger.debug("added kan called", caller_seat=caller_seat, tile_id=tile_id)
    # validate and resolve tile_id to the actual in-hand copy before chankan
    # checks, so the resolved tile is used consistently for prompts, scoring,
    # and kan execution.
    resolved_tile_id = resolve_added_kan_tile(
        round_state,
        caller_seat,
        tile_id,
        game_state.settings,
    )

    # check for chankan first (using current state before kan is executed)
    chankan_seats = is_chankan_possible(round_state, caller_seat, resolved_tile_id)
    if chankan_seats:
        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=resolved_tile_id,
            from_seat=caller_seat,
            pending_seats=frozenset(chankan_seats),
            callers=tuple(chankan_seats),
        )
        new_round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        new_game_state = game_state.model_copy(update={"round_state": new_round_state})
        chankan_callers: list[int | MeldCaller] = list(chankan_seats)
        events: list[GameEvent] = [
            CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=resolved_tile_id,
                from_seat=caller_seat,
                callers=chankan_callers,
                target="all",
            ),
        ]
        return new_round_state, new_game_state, events

    old_dora_count = len(round_state.wall.dora_indicators)
    new_round_state, meld = call_added_kan(round_state, caller_seat, resolved_tile_id, game_state.settings)
    tile_ids = list(meld.tiles)
    events = [
        MeldEvent(
            meld_type=MeldViewType.ADDED_KAN,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            called_tile_id=meld.called_tile,
            from_seat=meld.from_who,
        ),
    ]
    _maybe_emit_dora_event(old_dora_count, new_round_state, events)
    new_round_state, new_game_state, events, _aborted = _check_four_kans_abort(
        new_round_state,
        game_state,
        events,
    )
    return new_round_state, new_game_state, events


def process_meld_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    meld_input: MeldCallInput,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Process a meld call (pon, chi, open kan, closed kan, added kan).

    For pon/chi/open kan: the tile_id is the discarded tile being called.
    For closed kan: tile_id is one of the 4 tiles to kan.
    For added kan: tile_id is the 4th tile to add to existing pon.

    Returns (new_round_state, new_game_state, events).
    """
    caller_seat = meld_input.caller_seat
    call_type = meld_input.call_type
    tile_id = meld_input.tile_id
    discarder_seat = round_state.current_player_seat

    if call_type == MeldCallType.PON:
        return _process_pon_call(round_state, game_state, caller_seat, discarder_seat, tile_id)

    if call_type == MeldCallType.CHI:
        if meld_input.sequence_tiles is None:
            logger.error("chi call missing sequence_tiles", caller_seat=caller_seat)
            raise InvalidMeldError("chi call requires sequence_tiles")
        return _process_chi_call(
            round_state,
            game_state,
            caller_seat,
            tile_id,
            meld_input.sequence_tiles,
        )

    if call_type == MeldCallType.OPEN_KAN:
        return _process_open_kan_call(round_state, game_state, caller_seat, discarder_seat, tile_id)

    if call_type == MeldCallType.CLOSED_KAN:
        return _process_closed_kan_call(round_state, game_state, caller_seat, tile_id)

    if call_type == MeldCallType.ADDED_KAN:
        return _process_added_kan_call(round_state, game_state, caller_seat, tile_id)

    logger.error("unknown call_type", call_type=call_type, caller_seat=caller_seat)  # pragma: no cover
    raise InvalidActionError(f"unknown call_type: {call_type}")  # pragma: no cover
