from typing import TYPE_CHECKING

from game.logic.decision import Action, CallAnswer, Chi, Discard, Kan, Pon, Riichi, Ron, Tsumo
from game.logic.enums import KanType, MeldCallType, PlayerAction
from game.logic.tiles import tile_to_34

if TYPE_CHECKING:
    from game.logic.ai_player import AIPlayer
    from game.logic.state import Caller, MahjongPlayer, MahjongRoundState, MeldOption


class AIPlayerController:
    """
    Decision-maker for AI players.

    Provides methods to check AI player identity and get AI player decisions for turn actions and call responses. Does
    not orchestrate game flow.
    """

    def __init__(self, ai_players: dict[int, AIPlayer]) -> None:
        self._ai_players = ai_players

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

    def remove_ai_player(self, seat: int) -> None:
        """
        Remove an AI player from a seat (for reconnection).
        """
        self._ai_players.pop(seat, None)

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
    ) -> Action | None:
        """
        Get the AI player's turn action for an AI seat.

        Returns None when the AI picked an action this controller cannot dispatch.
        """
        player = round_state.players[seat]
        action = self._ai_players[seat].get_action(player, round_state)

        if action.action == PlayerAction.TSUMO:
            return Tsumo()

        if action.action == PlayerAction.RIICHI and action.tile_id is not None:
            return Riichi(tile=action.tile_id)

        if action.action == PlayerAction.DISCARD and action.tile_id is not None:
            return Discard(tile=action.tile_id)

        return None

    def get_call_response(
        self,
        *,
        round_state: MahjongRoundState,
        tile_id: int,
        caller: Caller,
    ) -> CallAnswer | None:
        """
        Get an AI caller's response to a call prompt.

        A caller offered ron decides on it first; one that declines it, or a meld-only caller, is asked about its melds
        in offer order (kan, pon, chi) and makes the first one it accepts. Returns None if the AI player declines
        everything (passes).
        """
        ai_player = self._ai_players[caller.seat]
        player = round_state.players[caller.seat]
        if caller.can_ron and ai_player.should_call_ron(player, discarded_tile=tile_id, round_state=round_state):
            return Ron()

        for meld in caller.melds:
            response = _get_meld_response(ai_player, player, meld=meld, tile_id=tile_id, round_state=round_state)
            if response is not None:
                return response

        return None


def _get_meld_response(
    ai_player: AIPlayer,
    player: MahjongPlayer,
    meld: MeldOption,
    tile_id: int,
    round_state: MahjongRoundState,
) -> CallAnswer | None:
    """
    Resolve AI player's meld response.

    Returns the call, or None if AI player declines.
    """
    meld_call_type = meld.call_type

    if meld_call_type == MeldCallType.PON and ai_player.should_call_pon(
        player, discarded_tile=tile_id, round_state=round_state
    ):
        return Pon()

    if meld_call_type == MeldCallType.CHI:
        chi_tiles = ai_player.should_call_chi(
            player, discarded_tile=tile_id, chi_options=meld.options, round_state=round_state
        )
        if chi_tiles is not None:
            return Chi(tiles=chi_tiles)

        return None

    if meld_call_type == MeldCallType.OPEN_KAN and ai_player.should_call_kan(
        player,
        kan_type=KanType.OPEN,
        tile_34=tile_to_34(tile_id),
        round_state=round_state,
    ):
        return Kan(kan_type=KanType.OPEN, tile=tile_id)

    return None
