from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from game.logic.enums import GameAction, TimeoutType
    from game.logic.events import ServiceEvent
    from game.logic.settings import GameSettings
    from game.logic.state import MahjongGameState
    from game.logic.types import ReconnectionSnapshot


@dataclass(frozen=True)
class GameStart:
    """
    The outcome of starting a game: its initial events and the seat of each input player, in input order.
    """

    events: list[ServiceEvent]
    seats: tuple[int, ...]


class GameService(Protocol):
    """
    Interface of the game logic, used by the session and the replay runner.

    Players are identified by seat; names are display only. Events returned by methods include a 'target' field:
    - "all": broadcast to all players in the game
    - "seat_0", "seat_1", etc.: send only to player at that seat
    """

    def handle_action(
        self,
        *,
        game_id: str,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> list[ServiceEvent]:
        """
        Handle a game action from the player at a seat.

        Returns a list of service events to broadcast.
        """
        ...

    def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
    ) -> GameStart:
        """
        Start a game with the given players, seating AI players in the empty seats.

        Returns the initial state events (one per player with their view) and each input player's seat, in input order.
        When seed is provided, the game is deterministically reproducible. When seed is None, a random seed is
        generated. When settings is provided, the game uses the given settings. When wall is provided, use it instead of
        generating from seed.
        """
        ...

    def get_game_seed(self, game_id: str) -> str | None:
        """
        Return the seed for a game, or None if game doesn't exist.
        """
        ...

    def get_game_state(self, game_id: str) -> MahjongGameState | None:
        """
        Return the current game state, or None if game doesn't exist.
        """
        ...

    def handle_timeout(
        self,
        *,
        game_id: str,
        seat: int,
        timeout_type: TimeoutType,
    ) -> list[ServiceEvent]:
        """
        Handle a seat's timeout by performing the default action.

        For TURN timeout: tsumogiri (discard last drawn tile).
        For MELD timeout: pass on the call opportunity.
        For ROUND_ADVANCE timeout: auto-confirm round advancement.
        """
        ...

    def cleanup_game(self, game_id: str) -> None:
        """
        Remove all game state for a game that was abandoned or cleaned up externally.
        """
        ...

    def replace_with_ai_player(self, game_id: str, seat: int) -> None:
        """
        Replace a disconnected player with an AI player at their seat.

        Called when a player disconnects mid-game.
        """
        ...

    def process_ai_player_actions_after_replacement(
        self,
        game_id: str,
        seat: int,
    ) -> list[ServiceEvent]:
        """
        Process pending AI player actions after a player was replaced with an AI player.

        Handles the case where the replaced player had a pending turn or call.
        """
        ...

    def restore_human_player(self, game_id: str, seat: int) -> None:
        """
        Remove the AI player at a seat and restore it for human control.
        """
        ...

    def build_reconnection_snapshot(self, game_id: str, seat: int) -> ReconnectionSnapshot | None:
        """
        Build a full game state snapshot for a reconnecting player at the given seat.

        Must be called after restore_human_player() so the AI player flag is correct.
        """
        ...

    def build_draw_event_for_seat(self, game_id: str, seat: int) -> list[ServiceEvent]:
        """
        Rebuild the draw event with available actions for a specific seat.
        """
        ...

    def is_round_advance_pending(self, game_id: str) -> bool:
        """
        Check if a round advance is waiting for player confirmation.
        """
        ...

    def get_pending_round_advance_seats(self, game_id: str) -> list[int]:
        """
        Return the seats that still need to confirm round advance, in seat order.
        """
        ...
