from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.logic.events import DrawEvent, DrawNoticeEvent, GameEvent, SeatTarget
from game.logic.settings import NUM_PLAYERS
from game.logic.wall import tiles_remaining

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState


@dataclass(frozen=True)
class ActionResult:
    """
    An accepted action: its events and the game state after it, which the service stores.

    Defined outside action_handlers so that call_resolution and the other handler subsystems can import it without an
    import cycle.
    """

    events: list[GameEvent]
    state: MahjongGameState


def create_draw_events(game_state: MahjongGameState, seat: int, tile_id: int) -> list[GameEvent]:
    """
    Create a player's draw, with the live wall left after it, then its notice to each other seat in seat order.
    """
    draw = DrawEvent(
        seat=seat,
        tile_id=tile_id,
        tiles_remaining=tiles_remaining(game_state.round_state.wall),
        target=SeatTarget(seat=seat),
    )
    notices = [
        DrawNoticeEvent(seat=seat, target=SeatTarget(seat=other)) for other in range(NUM_PLAYERS) if other != seat
    ]
    return [draw, *notices]
