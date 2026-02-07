"""Shared result type and helpers for action handler execution.

This module provides the ActionResult type and shared helpers used by
action handlers and the game service. It lives in a neutral module to
avoid import cycles between action_handlers and extracted subsystem
modules (e.g., call_resolution).
"""

from typing import NamedTuple

from game.logic.actions import get_available_actions
from game.logic.events import GameEvent, TurnEvent
from game.logic.state import MahjongGameState, MahjongRoundState


class ActionResult(NamedTuple):
    """
    Result of an action handler execution.

    Contains the events produced by the action and optionally the new
    immutable state after the action. When new_round_state and new_game_state
    are provided, the caller should use them to update its stored state.
    """

    events: list[GameEvent]
    needs_post_discard: bool = False
    new_round_state: MahjongRoundState | None = None
    new_game_state: MahjongGameState | None = None


def create_turn_event(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
) -> TurnEvent:
    """Create a turn event for a player with available actions."""
    available_actions = get_available_actions(round_state, game_state, seat)
    return TurnEvent(
        current_seat=seat,
        available_actions=available_actions,
        wall_count=len(round_state.wall),
        target=f"seat_{seat}",
    )
