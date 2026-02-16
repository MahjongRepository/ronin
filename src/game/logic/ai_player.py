"""
AI player decision making for mahjong game.

Tsumogiri AI player: always discards the last drawn tile and passes on all calls.
"""

from enum import Enum
from typing import TYPE_CHECKING

from game.logic.enums import KanType, PlayerAction
from game.logic.types import AIPlayerAction

if TYPE_CHECKING:
    from game.logic.state import (
        MahjongPlayer,
        MahjongRoundState,
    )


class AIPlayerStrategy(Enum):
    """Available AI player strategies."""

    TSUMOGIRI = "tsumogiri"


class AIPlayer:
    """
    AI player with configurable decision-making strategy.

    All decision methods are on this class so subclasses or alternative strategies
    can override them. The base implementation is tsumogiri: always discard the
    last drawn tile and pass on all call opportunities.
    """

    def __init__(self, strategy: AIPlayerStrategy = AIPlayerStrategy.TSUMOGIRI) -> None:
        self.strategy = strategy

    def should_call_pon(
        self,
        player: MahjongPlayer,
        discarded_tile: int,
        round_state: MahjongRoundState,
    ) -> bool:
        """Decide whether to call pon on a discarded tile."""
        return False

    def should_call_chi(
        self,
        player: MahjongPlayer,
        discarded_tile: int,
        chi_options: tuple[tuple[int, int], ...] | None,
        round_state: MahjongRoundState,
    ) -> tuple[int, int] | None:
        """
        Choose a chi option, or return None to decline.

        Returns the chosen (tile_a, tile_b) pair from chi_options, or None to pass.
        """
        return None

    def should_call_kan(
        self,
        player: MahjongPlayer,
        kan_type: KanType,
        tile_34: int,
        round_state: MahjongRoundState,
    ) -> bool:
        """Decide whether to call kan."""
        return False

    def should_call_ron(
        self,
        player: MahjongPlayer,
        discarded_tile: int,
        round_state: MahjongRoundState,
    ) -> bool:
        """Decide whether to call ron on a discarded tile."""
        return False

    def select_discard(
        self,
        player: MahjongPlayer,
        round_state: MahjongRoundState,
    ) -> int:
        """
        Select a tile to discard from the player's hand.

        Always discards the last tile (most recently drawn).
        """
        if not player.tiles:
            raise ValueError("cannot select discard from empty hand")
        return player.tiles[-1]

    def get_action(
        self,
        player: MahjongPlayer,
        round_state: MahjongRoundState,
    ) -> AIPlayerAction:
        """
        Determine the AI player's turn action.

        Always discards the last drawn tile.
        """
        discard_tile = self.select_discard(player, round_state)
        return AIPlayerAction(action=PlayerAction.DISCARD, tile_id=discard_tile)
