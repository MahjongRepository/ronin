from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.abortive import can_call_kyuushu_kyuuhai
from game.logic.decision import (
    Action,
    CallOpportunity,
    CallSource,
    Chi,
    Decision,
    Discard,
    Kan,
    Kyuushu,
    Pass,
    Pon,
    Riichi,
    Ron,
    Tsumo,
    TurnAfterCall,
    TurnAfterDraw,
)
from game.logic.enums import KanType, MeldCallType, PlayerAction, PromptKind
from game.logic.melds import get_possible_added_kans, get_possible_closed_kans
from game.logic.riichi import can_declare_riichi, riichi_discards
from game.logic.round import choose_default_discard, legal_discards
from game.logic.tiles import tile_to_34
from game.logic.types import AvailableActionItem
from game.logic.win import can_declare_tsumo, is_haitei, is_houtei

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState, MahjongPlayer, PendingCallPrompt


def get_available_actions(game_state: MahjongGameState, seat: int) -> list[AvailableActionItem]:
    """
    Return available actions for a player at their turn.

    The single source of a draw's offered actions, for the draw event and its reconnect rebuild alike. Discard is
    always available: the client may discard any tile in hand, in riichi only the drawn one; the kuikae types it may
    not discard right after its own pon or chi come with that turn's event instead.

    Includes:
    - riichi option (if eligible), with the tile ids whose discard keeps the hand in tenpai
    - tsumo option (if hand is winning and the player drew; never right after their own pon or chi)
    - kan options (closed and added)
    - kyuushu kyuuhai (if enabled and eligible on the player's first uninterrupted draw)
    """
    settings = game_state.settings
    round_state = game_state.round_state
    player = round_state.players[seat]

    result: list[AvailableActionItem] = []

    # check riichi eligibility
    if can_declare_riichi(player, round_state, settings=settings):
        result.append(AvailableActionItem(action=PlayerAction.RIICHI, tiles=riichi_discards(player)))

    # check tsumo
    if can_declare_tsumo(player, round_state, settings=settings):
        result.append(AvailableActionItem(action=PlayerAction.TSUMO))

    # check kan options
    closed_kans = get_possible_closed_kans(player, round_state, settings=settings)
    if closed_kans:
        result.append(AvailableActionItem(action=PlayerAction.KAN, tiles=closed_kans))

    added_kans = get_possible_added_kans(player, round_state, settings=settings)
    if added_kans:
        result.append(AvailableActionItem(action=PlayerAction.ADDED_KAN, tiles=added_kans))

    if can_call_kyuushu_kyuuhai(player, round_state, settings=settings):
        result.append(AvailableActionItem(action=PlayerAction.KYUUSHU))

    return result


def build_decision(game_state: MahjongGameState, seat: int) -> Decision:
    """
    Build the decision of a seat the game awaits: its answer to the pending call prompt, else its turn.
    """
    prompt = game_state.round_state.pending_call_prompt
    if prompt is not None:
        return _call_decision(game_state, prompt, seat=seat)

    return _turn_decision(game_state, seat)


def _turn_decision(game_state: MahjongGameState, seat: int) -> Decision:
    """
    Build a turn's decision: the legal discards in hand order, then the offered actions in get_available_actions order.

    Right after the seat's own pon or chi it drew nothing and is offered nothing but the discards kuikae leaves.
    """
    round_state = game_state.round_state
    player = round_state.players[seat]
    discards = [Discard(tile=tile) for tile in legal_discards(player)]
    offers = [action for item in get_available_actions(game_state, seat) for action in _offered_actions(player, item)]
    if round_state.is_after_meld_call:
        context: TurnAfterDraw | TurnAfterCall = TurnAfterCall(kuikae=player.kuikae_tiles)
    else:
        context = TurnAfterDraw(
            drawn=player.tiles[-1], rinshan=player.is_rinshan, haitei=is_haitei(player, round_state)
        )

    default = Discard(tile=choose_default_discard(player))
    return Decision(seat=seat, context=context, legal=(*discards, *offers), default=default)


def _offered_actions(player: MahjongPlayer, item: AvailableActionItem) -> list[Action]:
    """
    Return the actions one offered turn action stands for; a kan of a tile type names the first held copy of it.
    """
    tiles = item.tiles or []
    match item.action:
        case PlayerAction.RIICHI:
            return [Riichi(tile=tile) for tile in tiles]
        case PlayerAction.TSUMO:
            return [Tsumo()]
        case PlayerAction.KAN:
            return [Kan(kan_type=KanType.CLOSED, tile=_first_held_copy(player, tile_34)) for tile_34 in tiles]
        case PlayerAction.ADDED_KAN:
            return [Kan(kan_type=KanType.ADDED, tile=_first_held_copy(player, tile_34)) for tile_34 in tiles]
        case PlayerAction.KYUUSHU:
            return [Kyuushu()]
        case _:  # pragma: no cover (exhaustive)
            raise AssertionError(f"turn action {item.action} is never offered")


def _first_held_copy(player: MahjongPlayer, tile_34: int) -> int:
    return next(tile for tile in player.tiles if tile_to_34(tile) == tile_34)


def _call_decision(game_state: MahjongGameState, prompt: PendingCallPrompt, *, seat: int) -> Decision:
    """
    Build a call's decision: a ron, then the seat's melds in offer order (open kan, pon, each chi shape), then a pass.
    """
    caller = prompt.caller(seat)
    legal: list[Action] = [Ron()] if caller.can_ron else []
    for meld in caller.melds:
        match meld.call_type:
            case MeldCallType.OPEN_KAN:
                legal.append(Kan(kan_type=KanType.OPEN, tile=prompt.tile_id))
            case MeldCallType.PON:
                legal.append(Pon())
            case MeldCallType.CHI:
                legal.extend(Chi(tiles=option) for option in meld.options or ())
            case _:  # pragma: no cover (exhaustive)
                raise AssertionError(f"meld {meld.call_type} is never offered on a call")

    context = CallOpportunity(
        tile=prompt.tile_id,
        from_seat=prompt.from_seat,
        source=_call_source(prompt),
        houtei=prompt.kind == PromptKind.DISCARD and is_houtei(game_state.round_state),
    )
    return Decision(seat=seat, context=context, legal=(*legal, Pass()), default=Pass())


def _call_source(prompt: PendingCallPrompt) -> CallSource:
    if prompt.kind == PromptKind.DISCARD:
        return CallSource.DISCARD

    return CallSource.ADDED_KAN if prompt.kan_type == KanType.ADDED else CallSource.CLOSED_KAN
