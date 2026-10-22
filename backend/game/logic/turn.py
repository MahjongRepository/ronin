from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from game.logic.abortive import (
    AbortiveDrawType,
    check_four_kans,
    check_four_riichi,
    check_four_winds,
    check_triple_ron,
    process_abortive_draw,
)
from game.logic.action_result import create_draw_event
from game.logic.enums import (
    MELD_CALL_PRIORITY,
    MeldCallType,
    MeldViewType,
    PromptKind,
    RoundPhase,
)
from game.logic.events import (
    DiscardEvent,
    DoraRevealedEvent,
    GameEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    build_call_prompt_events,
)
from game.logic.exceptions import (
    ImpossibleActionError,
    InvalidRiichiError,
    ScoringError,
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
    Caller,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    MeldOption,
    PendingCallPrompt,
)
from game.logic.state_utils import (
    advance_turn,
    update_player,
)
from game.logic.tiles import tile_to_34
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
    from game.logic.types import MeldCallInput, RonCallInput

logger = structlog.get_logger()


def _maybe_emit_dora_event(
    old_dora_count: int,
    new_round_state: MahjongRoundState,
    events: list[GameEvent],
) -> None:
    """
    Append DoraRevealedEvents for each new dora indicator revealed.
    """
    events.extend(
        DoraRevealedEvent(tile_id=indicator) for indicator in new_round_state.wall.dora_indicators[old_dora_count:]
    )


def emit_deferred_dora_events(
    round_state: MahjongRoundState,
) -> tuple[MahjongRoundState, list[GameEvent]]:
    """
    Reveal deferred dora indicators (from open/added kan) and emit events.

    Called after a discard passes the ron check. Under our rules, open/added kan dora is revealed only after the
    replacement discard is accepted (not ron'd).

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

    Draws a tile and emits the draw event with the player's available actions (get_available_actions).

    Returns (new_round_state, new_game_state, events).
    """
    events: list[GameEvent] = []
    current_seat = round_state.current_player_seat

    new_round_state, drawn_tile = draw_tile(round_state)
    if drawn_tile is None:
        logger.debug("exhaustive draw")
        new_round_state, new_game_state, result = process_exhaustive_draw(game_state)

        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(RoundEndEvent(result=result, target="all"))
        return new_round_state, new_game_state, events

    logger.debug("tile drawn", tile_id=drawn_tile)

    # update game state with new round state
    new_game_state = game_state.model_copy(update={"round_state": new_round_state})

    events.append(create_draw_event(new_round_state, new_game_state, seat=current_seat, tile_id=drawn_tile))
    return new_round_state, new_game_state, events


def _check_riichi_furiten(
    round_state: MahjongRoundState,
    tile_id: int,
    discarder_seat: int,
    ron_callers: list[int],
) -> MahjongRoundState:
    """
    Set riichi furiten for riichi players whose winning tile just passed.

    A riichi player who is waiting on the discarded tile but did not (or could not) call ron becomes permanently furiten
    for the rest of the hand.

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
) -> list[Caller]:
    """
    Find all players who can call a meld on the discarded tile.

    Returns the meld callers ordered by their best meld (kan > pon > chi), then seat index; each caller's melds are in
    that priority order too, a chi with its options.

    Last discard restriction: when the live wall is empty, no meld calls are
    allowed (only ron). This applies to the final discard of a hand.
    """
    if not round_state.wall.live_tiles:
        return []

    callers: list[Caller] = []
    for seat in range(NUM_PLAYERS):
        if seat == discarder_seat:
            continue

        player = round_state.players[seat]
        melds: list[MeldOption] = []
        if can_call_open_kan(player, discarded_tile=tile_id, round_state=round_state, settings=settings):
            melds.append(MeldOption(call_type=MeldCallType.OPEN_KAN))

        if can_call_pon(player, tile_id):
            melds.append(MeldOption(call_type=MeldCallType.PON))

        chi_options = can_call_chi(
            player, discarded_tile=tile_id, discarder_seat=discarder_seat, caller_seat=seat, settings=settings
        )
        if chi_options:
            melds.append(MeldOption(call_type=MeldCallType.CHI, options=tuple(chi_options)))

        if melds:
            callers.append(Caller(seat=seat, melds=tuple(melds)))

    callers.sort(key=lambda c: MELD_CALL_PRIORITY[c.melds[0].call_type])
    return callers


def _validate_riichi_discard(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    tile_id: int,
    settings: GameSettings,
) -> None:
    """
    Validate riichi declaration and that the discard keeps hand in tenpai.

    Raises ImpossibleActionError when riichi was not offered or the tile is not in hand, and InvalidRiichiError when the
    discard would leave the hand not tenpai.
    """
    if not can_declare_riichi(player, round_state, settings=settings):
        logger.warning("cannot declare riichi: conditions not met", seat=player.seat)
        raise ImpossibleActionError("cannot declare riichi: conditions not met")

    removed = False
    simulated: list[int] = []
    for t in player.tiles:
        if t == tile_id and not removed:
            removed = True
            continue

        simulated.append(t)

    if not removed:
        raise ImpossibleActionError(f"tile {tile_id} not in hand")

    if not is_tempai(tuple(simulated), player.melds):
        raise InvalidRiichiError(f"hand is not tenpai after discarding tile {tile_id}")


def _check_abortive_draw(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    draw_type: AbortiveDrawType,
    events: list[GameEvent],
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Produce abortive draw result and mark round finished.
    """
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
    meld_callers: list[Caller],
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Create the DISCARD call prompt for all callers, ron callers first, and its per-seat prompt events.
    """
    callers = (*(Caller(seat=seat, can_ron=True) for seat in ron_callers), *meld_callers)
    prompt = PendingCallPrompt(
        kind=PromptKind.DISCARD,
        tile_id=tile_id,
        from_seat=round_state.current_player_seat,
        pending_seats=frozenset(c.seat for c in callers),
        callers=callers,
    )
    new_round = round_state.model_copy(update={"pending_call_prompt": prompt})
    new_game = game_state.model_copy(update={"round_state": new_round})
    return new_round, new_game, list(build_call_prompt_events(prompt))


def _finalize_no_callers(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    current_seat: int,
    *,
    riichi_pending: bool,
    events: list[GameEvent],
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Handle the no-callers path: reveal deferred dora, finalize riichi, advance turn.
    """
    settings = game_state.settings
    new_round, dora_events = emit_deferred_dora_events(round_state)
    events.extend(dora_events)
    new_game = game_state.model_copy(update={"round_state": new_round})

    if riichi_pending:
        new_round, new_game = declare_riichi(new_round, new_game, seat=current_seat, settings=settings)
        events.append(RiichiDeclaredEvent(seat=current_seat, target="all"))

        if settings.has_suucha_riichi and check_four_riichi(new_round):
            return _check_abortive_draw(new_round, new_game, draw_type=AbortiveDrawType.FOUR_RIICHI, events=events)

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
        _validate_riichi_discard(player, round_state, tile_id=tile_id, settings=settings)
        riichi_pending = True

    new_round_state, discard = discard_tile(round_state, current_seat, tile_id, is_riichi=is_riichi)

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
        return _check_abortive_draw(new_round_state, game_state, draw_type=AbortiveDrawType.FOUR_WINDS, events=events)

    # find ron callers and apply riichi furiten
    ron_callers = _find_ron_callers(new_round_state, tile_id=tile_id, discarder_seat=current_seat, settings=settings)
    new_round_state = _check_riichi_furiten(
        new_round_state, tile_id=tile_id, discarder_seat=current_seat, ron_callers=ron_callers
    )

    if settings.has_triple_ron_abort and check_triple_ron(ron_callers, settings.triple_ron_count):
        return _check_abortive_draw(new_round_state, game_state, draw_type=AbortiveDrawType.TRIPLE_RON, events=events)

    # find meld callers (ron-dominant: seats with ron don't get meld options)
    ron_caller_set = set(ron_callers)
    all_meld_callers = _find_meld_callers(
        new_round_state, tile_id=tile_id, discarder_seat=current_seat, settings=settings
    )
    meld_callers = [c for c in all_meld_callers if c.seat not in ron_caller_set]

    if ron_callers or meld_callers:
        new_round, new_game, prompt_events = _build_discard_prompt(
            new_round_state,
            game_state,
            tile_id=tile_id,
            ron_callers=ron_callers,
            meld_callers=meld_callers,
        )
        return new_round, new_game, events + prompt_events

    return _finalize_no_callers(
        new_round_state,
        game_state,
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
        if can_call_ron(player, discarded_tile=tile_id, round_state=round_state, settings=settings):
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
        hand_result = calculate_hand_value_with_tiles(ctx, tiles=tiles_with_win, win_tile=tile_id)
        if hand_result.error:
            logger.error("ron calculation error", winner_seat=winner_seat, error=hand_result.error)
            raise ScoringError(f"ron calculation error: {hand_result.error}")

        new_round_state, new_game_state, result = apply_ron_score(
            game_state,
            winner_seat=winner_seat,
            loser_seat=discarder_seat,
            hand_result=hand_result,
            winning_tile=tile_id,
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

    else:
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
            hand_result = calculate_hand_value_with_tiles(ctx, tiles=tiles_with_win, win_tile=tile_id)
            if hand_result.error:
                logger.error("ron calculation error", winner_seat=winner_seat, error=hand_result.error)
                raise ScoringError(f"ron calculation error for seat {winner_seat}: {hand_result.error}")

            winners.append((winner_seat, hand_result))

        new_round_state, new_game_state, result = apply_double_ron_score(
            game_state,
            winners=winners,
            loser_seat=discarder_seat,
            winning_tile=tile_id,
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
    if not can_declare_tsumo(winner, round_state, settings=settings):
        logger.warning("cannot declare tsumo: conditions not met", seat=winner_seat)
        raise ImpossibleActionError("cannot declare tsumo: conditions not met")

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
        raise ScoringError(f"tsumo calculation error: {hand_result.error}")

    # apply score changes
    new_game_state = game_state.model_copy(update={"round_state": new_round_state})
    new_round_state, new_game_state, result = apply_tsumo_score(
        new_game_state, winner_seat=winner_seat, hand_result=hand_result
    )
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
    """
    Handle a pon meld call.
    """
    logger.debug("pon called", caller_seat=caller_seat, from_seat=discarder_seat, tile_id=tile_id)
    new_round_state, meld = call_pon(
        round_state,
        caller_seat=caller_seat,
        discarder_seat=discarder_seat,
        tile_id=tile_id,
        settings=game_state.settings,
    )
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
    """
    Handle a chi meld call.
    """
    logger.debug("chi called", caller_seat=caller_seat, tile_id=tile_id, sequence_tiles=sequence_tiles)
    discarder_seat = round_state.current_player_seat
    new_round_state, meld = call_chi(
        round_state,
        caller_seat=caller_seat,
        discarder_seat=discarder_seat,
        tile_id=tile_id,
        sequence_tiles=sequence_tiles,
        settings=game_state.settings,
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
    """
    Check for four kans abortive draw.

    Return (round, game, events, aborted).
    """
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
    """
    Handle an open kan meld call.
    """
    logger.debug("open kan called", caller_seat=caller_seat, from_seat=discarder_seat, tile_id=tile_id)

    old_dora_count = len(round_state.wall.dora_indicators)
    new_round_state, meld = call_open_kan(
        round_state,
        caller_seat=caller_seat,
        discarder_seat=discarder_seat,
        tile_id=tile_id,
        settings=game_state.settings,
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
    _maybe_emit_dora_event(old_dora_count=old_dora_count, new_round_state=new_round_state, events=events)

    new_round_state, new_game_state, events, _aborted = _check_four_kans_abort(
        new_round_state,
        game_state,
        events=events,
    )
    return new_round_state, new_game_state, events


def _build_chankan_prompt(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    *,
    caller_seat: int,
    tile_id: int,
    seats: list[int],
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Create the CHANKAN call prompt for the seats that can rob the kan, and its per-seat prompt events.
    """
    prompt = PendingCallPrompt(
        kind=PromptKind.CHANKAN,
        tile_id=tile_id,
        from_seat=caller_seat,
        pending_seats=frozenset(seats),
        callers=tuple(Caller(seat=seat, can_ron=True) for seat in seats),
    )
    new_round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
    new_game_state = game_state.model_copy(update={"round_state": new_round_state})
    return new_round_state, new_game_state, list(build_call_prompt_events(prompt))


def _process_closed_kan_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Handle a closed kan meld call.
    """
    logger.debug("closed kan called", caller_seat=caller_seat, tile_id=tile_id)

    # validate the closed kan is legal before checking for kokushi chankan,
    # so a forged payload cannot trigger a chankan window for an illegal kan
    validate_closed_kan(round_state, seat=caller_seat, tile_id=tile_id, settings=game_state.settings)

    # kokushi musou may rob a closed kan; check before executing
    kokushi_seats = is_kokushi_chankan_possible(round_state, caller_seat=caller_seat, kan_tile=tile_id)
    if kokushi_seats:
        return _build_chankan_prompt(
            round_state, game_state, caller_seat=caller_seat, tile_id=tile_id, seats=kokushi_seats
        )

    old_dora_count = len(round_state.wall.dora_indicators)
    new_round_state, meld = call_closed_kan(
        round_state, seat=caller_seat, tile_id=tile_id, settings=game_state.settings
    )
    tile_ids = list(meld.tiles)
    events: list[GameEvent] = [
        MeldEvent(
            meld_type=MeldViewType.CLOSED_KAN,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
        ),
    ]
    _maybe_emit_dora_event(old_dora_count=old_dora_count, new_round_state=new_round_state, events=events)

    new_round_state, new_game_state, events, _aborted = _check_four_kans_abort(
        new_round_state,
        game_state,
        events=events,
    )
    return new_round_state, new_game_state, events


def _process_added_kan_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Handle an added kan meld call.
    """
    logger.debug("added kan called", caller_seat=caller_seat, tile_id=tile_id)
    # validate and resolve tile_id to the actual in-hand copy before chankan
    # checks, so the resolved tile is used consistently for prompts, scoring,
    # and kan execution.
    resolved_tile_id = resolve_added_kan_tile(
        round_state,
        seat=caller_seat,
        tile_id=tile_id,
        settings=game_state.settings,
    )

    # check for chankan first (using current state before kan is executed)
    chankan_seats = is_chankan_possible(round_state, caller_seat=caller_seat, kan_tile=resolved_tile_id)
    if chankan_seats:
        return _build_chankan_prompt(
            round_state, game_state, caller_seat=caller_seat, tile_id=resolved_tile_id, seats=chankan_seats
        )

    old_dora_count = len(round_state.wall.dora_indicators)
    new_round_state, meld = call_added_kan(
        round_state, seat=caller_seat, tile_id=resolved_tile_id, settings=game_state.settings
    )
    tile_ids = list(meld.tiles)
    events: list[GameEvent] = [
        MeldEvent(
            meld_type=MeldViewType.ADDED_KAN,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            called_tile_id=meld.called_tile,
            from_seat=meld.from_who,
        ),
    ]
    _maybe_emit_dora_event(old_dora_count=old_dora_count, new_round_state=new_round_state, events=events)

    new_round_state, new_game_state, events, _aborted = _check_four_kans_abort(
        new_round_state,
        game_state,
        events=events,
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

    match call_type:
        case MeldCallType.PON:
            return _process_pon_call(
                round_state, game_state, caller_seat=caller_seat, discarder_seat=discarder_seat, tile_id=tile_id
            )
        case MeldCallType.CHI:
            if meld_input.sequence_tiles is None:
                logger.error("chi call missing sequence_tiles", caller_seat=caller_seat)
                raise AssertionError("chi call requires sequence_tiles")

            return _process_chi_call(
                round_state,
                game_state,
                caller_seat=caller_seat,
                tile_id=tile_id,
                sequence_tiles=meld_input.sequence_tiles,
            )
        case MeldCallType.OPEN_KAN:
            return _process_open_kan_call(
                round_state, game_state, caller_seat=caller_seat, discarder_seat=discarder_seat, tile_id=tile_id
            )
        case MeldCallType.CLOSED_KAN:
            return _process_closed_kan_call(round_state, game_state, caller_seat=caller_seat, tile_id=tile_id)
        case MeldCallType.ADDED_KAN:
            return _process_added_kan_call(round_state, game_state, caller_seat=caller_seat, tile_id=tile_id)

    logger.error("unknown call_type", call_type=call_type, caller_seat=caller_seat)  # pragma: no cover (exhaustive)
    raise AssertionError(f"unknown call_type: {call_type}")  # pragma: no cover (exhaustive)
