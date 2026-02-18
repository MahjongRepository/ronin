"""
AI player controller as a pure decision-maker.

Provides AI player identification and decision methods.
Orchestration is handled by MahjongGameService.
"""

from typing import TYPE_CHECKING, Any

from game.logic.enums import CallType, GameAction, KanType, MeldCallType, PlayerAction
from game.logic.tiles import tile_to_34
from game.logic.types import MeldCaller

if TYPE_CHECKING:
    from game.logic.ai_player import AIPlayer
    from game.logic.state import MahjongPlayer, MahjongRoundState


class AIPlayerController:
    """
    Decision-maker for AI players.

    Provides methods to check AI player identity and get AI player decisions
    for turn actions and call responses. Does not orchestrate game flow.
    """

    def __init__(self, ai_players: dict[int, AIPlayer]) -> None:
        self._ai_players = ai_players

    def _get_ai_player(self, seat: int) -> AIPlayer | None:
        return self._ai_players.get(seat)

    def is_ai_player(self, seat: int) -> bool:
        """Check if a seat is occupied by an AI player."""
        return seat in self._ai_players

    def add_ai_player(self, seat: int, ai_player: AIPlayer) -> None:
        """Register an AI player at a seat (replacing a disconnected player)."""
        self._ai_players[seat] = ai_player

    def remove_ai_player(self, seat: int) -> None:
        """Remove an AI player from a seat (for reconnection)."""
        self._ai_players.pop(seat, None)

    @property
    def ai_player_seats(self) -> set[int]:
        """Return the set of seats occupied by AI players."""
        return set(self._ai_players.keys())

    def get_turn_action(
        self,
        seat: int,
        round_state: MahjongRoundState,
    ) -> tuple[GameAction, dict[str, Any]] | None:
        """
        Get the AI player's turn action as (GameAction, data).

        Returns None if seat is not an AI player.
        """
        ai_player = self._get_ai_player(seat)
        if ai_player is None:
            return None

        player = round_state.players[seat]
        action = ai_player.get_action(player, round_state)

        if action.action == PlayerAction.TSUMO:
            return GameAction.DECLARE_TSUMO, {}

        if action.action == PlayerAction.RIICHI:
            return GameAction.DECLARE_RIICHI, {"tile_id": action.tile_id}

        if action.action == PlayerAction.DISCARD:
            return GameAction.DISCARD, {"tile_id": action.tile_id}

        return None

    def get_call_response(
        self,
        seat: int,
        round_state: MahjongRoundState,
        call_type: CallType,
        tile_id: int,
        caller_info: int | MeldCaller,
    ) -> tuple[GameAction, dict[str, Any]] | None:
        """
        Get the AI player's call response as (GameAction, data).

        Returns None if the AI player declines (passes).
        """
        ai_player = self._get_ai_player(seat)
        if ai_player is None:
            return None

        player = round_state.players[seat]

        # Ron opportunity (standalone RON, CHANKAN, or ron caller within DISCARD prompt)
        if call_type in (CallType.RON, CallType.CHANKAN) or (
            call_type == CallType.DISCARD and isinstance(caller_info, int)
        ):
            if ai_player.should_call_ron(player, tile_id, round_state):
                return GameAction.CALL_RON, {}
            return None

        # Meld opportunity (standalone MELD or meld caller within DISCARD prompt)
        if isinstance(caller_info, MeldCaller):
            return _get_meld_response(ai_player, player, caller_info, tile_id, round_state)

        return None


def _get_meld_response(
    ai_player: AIPlayer,
    player: MahjongPlayer,
    caller_info: MeldCaller,
    tile_id: int,
    round_state: MahjongRoundState,
) -> tuple[GameAction, dict[str, Any]] | None:
    """
    Resolve AI player's meld response.

    Returns (GameAction, data) or None if AI player declines.
    """
    meld_call_type = caller_info.call_type

    if meld_call_type == MeldCallType.PON and ai_player.should_call_pon(player, tile_id, round_state):
        return GameAction.CALL_PON, {"tile_id": tile_id}

    if meld_call_type == MeldCallType.CHI:
        chi_tiles = ai_player.should_call_chi(player, tile_id, caller_info.options, round_state)
        if chi_tiles is not None:
            return GameAction.CALL_CHI, {"tile_id": tile_id, "sequence_tiles": chi_tiles}
        return None

    if meld_call_type == MeldCallType.OPEN_KAN and ai_player.should_call_kan(
        player,
        KanType.OPEN,
        tile_to_34(tile_id),
        round_state,
    ):
        return GameAction.CALL_KAN, {"tile_id": tile_id, "kan_type": KanType.OPEN}

    return None
