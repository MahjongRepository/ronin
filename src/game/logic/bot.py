"""
Bot decision making for mahjong game.

Tsumogiri bot: always discards the last drawn tile and passes on all calls.
"""

from enum import Enum
from typing import TYPE_CHECKING

from game.logic.enums import KanType, PlayerAction
from game.logic.types import BotAction

if TYPE_CHECKING:
    from game.logic.state import (
        MahjongPlayer,
        MahjongRoundState,
    )


class BotStrategy(Enum):
    """Available bot strategies."""

    TSUMOGIRI = "tsumogiri"


class BotPlayer:
    """
    Bot player with tsumogiri decision-making strategy.
    """

    def __init__(self, strategy: BotStrategy = BotStrategy.TSUMOGIRI) -> None:
        self.strategy = strategy


def should_call_pon(
    bot: BotPlayer,  # noqa: ARG001
    player: MahjongPlayer,  # noqa: ARG001
    discarded_tile: int,  # noqa: ARG001
    round_state: MahjongRoundState,  # noqa: ARG001
) -> bool:
    """
    Decide whether bot should call pon on a discarded tile.
    """
    return False


def should_call_chi(
    bot: BotPlayer,  # noqa: ARG001
    player: MahjongPlayer,  # noqa: ARG001
    discarded_tile: int,  # noqa: ARG001
    chi_options: tuple[tuple[int, int], ...] | None,  # noqa: ARG001
    round_state: MahjongRoundState,  # noqa: ARG001
) -> tuple[int, int] | None:
    """
    Decide whether bot should call chi on a discarded tile.
    """
    return None


def should_call_kan(
    bot: BotPlayer,  # noqa: ARG001
    player: MahjongPlayer,  # noqa: ARG001
    kan_type: KanType,  # noqa: ARG001
    tile_34: int,  # noqa: ARG001
    round_state: MahjongRoundState,  # noqa: ARG001
) -> bool:
    """
    Decide whether bot should call kan.
    """
    return False


def should_call_ron(
    bot: BotPlayer,  # noqa: ARG001
    player: MahjongPlayer,  # noqa: ARG001
    discarded_tile: int,  # noqa: ARG001
    round_state: MahjongRoundState,  # noqa: ARG001
) -> bool:
    """
    Decide whether bot should call ron.
    """
    return False


def select_discard(
    bot: BotPlayer,  # noqa: ARG001
    player: MahjongPlayer,
    round_state: MahjongRoundState,  # noqa: ARG001
) -> int:
    """
    Select a tile to discard from the player's hand.

    Always discards the last tile (most recently drawn).
    """
    if not player.tiles:
        raise ValueError("cannot select discard from empty hand")
    return player.tiles[-1]


def get_bot_action(
    bot: BotPlayer,
    player: MahjongPlayer,
    round_state: MahjongRoundState,
) -> BotAction:
    """
    Determine the bot's action during their turn.

    Always discards the last drawn tile.
    """
    discard_tile = select_discard(bot, player, round_state)
    return BotAction(action=PlayerAction.DISCARD, tile_id=discard_tile)
