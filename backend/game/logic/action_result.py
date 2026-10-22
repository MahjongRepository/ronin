from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.logic.actions import get_available_actions
from game.logic.events import DrawEvent, GameEvent, SeatTarget

if TYPE_CHECKING:
    from game.logic.enums import GameErrorCode
    from game.logic.state import MahjongGameState


@dataclass(frozen=True)
class ActionResult:
    """
    An accepted action: its events and the game state after it, which the service stores.

    needs_post_discard marks an accepted discard: when it opened no call prompt, the service draws for the next player.
    Defined outside action_handlers so that call_resolution and the other handler subsystems can import it without an
    import cycle.
    """

    events: list[GameEvent]
    state: MahjongGameState
    needs_post_discard: bool = False


@dataclass(frozen=True)
class Refusal:
    """
    A refused action: nothing changed, and the service answers the acting seat with an ErrorEvent of this code.
    """

    code: GameErrorCode
    message: str


def create_draw_event(game_state: MahjongGameState, seat: int, tile_id: int) -> DrawEvent:
    """
    Create a draw event for a player with available actions.
    """
    available_actions = get_available_actions(game_state, seat=seat)
    return DrawEvent(
        seat=seat,
        tile_id=tile_id,
        available_actions=available_actions,
        target=SeatTarget(seat=seat),
    )
