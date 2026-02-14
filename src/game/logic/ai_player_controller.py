"""
AI player controller as a pure decision-maker.

Provides AI player identification and decision methods.
Orchestration is handled by MahjongGameService.
"""

from typing import Any

from game.logic.ai_player import (
    AIPlayer,
    get_ai_player_action,
    should_call_chi,
    should_call_kan,
    should_call_pon,
    should_call_ron,
)
from game.logic.enums import CallType, GameAction, KanType, MeldCallType, PlayerAction
from game.logic.state import (
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.types import MeldCaller


class AIPlayerController:
    """
    Decision-maker for AI players.

    Provides methods to check AI player identity and get AI player decisions
    for turn actions and call responses. Does not orchestrate game flow.
    """

    def __init__(self, ai_players: dict[int, AIPlayer]) -> None:
        """
        Initialize AI player controller with seat-to-AI-player mapping.
        """
        self._ai_players = ai_players

    def _get_ai_player(self, seat: int) -> AIPlayer | None:
        """
        Get the AI player instance for a given seat.
        """
        return self._ai_players.get(seat)

    def is_ai_player(self, seat: int) -> bool:
        """
        Check if a seat is occupied by an AI player.
        """
        return seat in self._ai_players

    def add_ai_player(self, seat: int, ai_player: AIPlayer) -> None:
        """
        Register an AI player at a seat (replacing a disconnected player).
        """
        self._ai_players[seat] = ai_player

    @property
    def ai_player_seats(self) -> set[int]:
        """
        Return the set of seats occupied by AI players.
        """
        return set(self._ai_players.keys())

    def get_turn_action(
        self,
        seat: int,
        round_state: MahjongRoundState,
    ) -> tuple[GameAction, dict[str, Any]] | None:
        """
        Get the AI player's turn action as (action, data).

        Returns None if seat is not an AI player.
        """
        ai_player = self._get_ai_player(seat)
        if ai_player is None:
            return None

        player = round_state.players[seat]
        action = get_ai_player_action(ai_player, player, round_state)

        # map AI player action to GameAction + data dict for dispatch
        if action.action == PlayerAction.TSUMO:
            return GameAction.DECLARE_TSUMO, {}

        if action.action == PlayerAction.RIICHI:
            return GameAction.DECLARE_RIICHI, {"tile_id": action.tile_id}

        if action.action == PlayerAction.DISCARD:
            return GameAction.DISCARD, {"tile_id": action.tile_id}

        return None

    def get_call_response(  # noqa: PLR0911
        self,
        seat: int,
        round_state: MahjongRoundState,
        call_type: CallType,
        tile_id: int,
        caller_info: int | MeldCaller,
    ) -> tuple[GameAction, dict[str, Any]] | None:
        """
        Get the AI player's call response as (action, data).

        Returns None if the AI player declines (passes).
        """
        ai_player = self._get_ai_player(seat)
        if ai_player is None:
            return None

        player = round_state.players[seat]

        # ron/chankan opportunities
        if call_type in (CallType.RON, CallType.CHANKAN):
            if should_call_ron(ai_player, player, tile_id, round_state):
                return GameAction.CALL_RON, {}
            return None

        # unified discard prompt -- dispatch based on caller type
        if call_type == CallType.DISCARD:
            if isinstance(caller_info, int):
                # ron caller
                if should_call_ron(ai_player, player, tile_id, round_state):
                    return GameAction.CALL_RON, {}
                return None
            if isinstance(caller_info, MeldCaller):
                return _get_ai_player_meld_response(ai_player, player, caller_info, tile_id, round_state)
            return None

        # meld opportunities
        if call_type == CallType.MELD and isinstance(caller_info, MeldCaller):
            return _get_ai_player_meld_response(ai_player, player, caller_info, tile_id, round_state)

        return None


def _get_ai_player_meld_response(
    ai_player: AIPlayer,
    player: MahjongPlayer,
    caller_info: MeldCaller,
    tile_id: int,
    round_state: MahjongRoundState,
) -> tuple[GameAction, dict[str, Any]] | None:
    """
    Check AI player's meld response.

    Returns (action, data) or None if AI player declines.
    """
    meld_call_type = caller_info.call_type

    if meld_call_type == MeldCallType.PON and should_call_pon(ai_player, player, tile_id, round_state):
        return GameAction.CALL_PON, {"tile_id": tile_id}

    if meld_call_type == MeldCallType.CHI and should_call_chi(
        ai_player, player, tile_id, caller_info.options, round_state
    ):
        if caller_info.options:
            return GameAction.CALL_CHI, {"tile_id": tile_id, "sequence_tiles": caller_info.options[0]}
        return None

    if meld_call_type == MeldCallType.OPEN_KAN and should_call_kan(
        ai_player, player, KanType.OPEN, tile_id, round_state
    ):
        return GameAction.CALL_KAN, {"tile_id": tile_id, "kan_type": KanType.OPEN}

    return None
