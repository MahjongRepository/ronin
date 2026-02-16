from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from game.logic.enums import GameAction, TimeoutType
    from game.logic.events import ServiceEvent
    from game.logic.settings import GameSettings
    from game.logic.state import MahjongGameState


class GameService(ABC):
    """
    Abstract interface for game logic.

    Events returned by methods include a 'target' field:
    - "all": broadcast to all players in the game
    - "seat_0", "seat_1", etc.: send only to player at that seat
    """

    @abstractmethod
    async def handle_action(
        self,
        game_id: str,
        player_name: str,
        action: GameAction,
        data: dict[str, Any],
    ) -> list[ServiceEvent]:
        """
        Handle a game action from a player.

        Returns a list of service events to broadcast.
        """
        ...

    @abstractmethod
    async def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
    ) -> list[ServiceEvent]:
        """
        Start a game with the given players.

        Returns a list of initial state events (one per player with their view).
        When seed is provided, the game is deterministically reproducible.
        When seed is None, a random seed is generated.
        When settings is provided, the game uses the given settings.
        When wall is provided, use it instead of generating from seed.
        """
        ...

    @abstractmethod
    def get_player_seat(self, game_id: str, player_name: str) -> int | None:
        """
        Get the seat number for a player by name.
        """
        ...

    @abstractmethod
    def get_game_seed(self, game_id: str) -> str | None:
        """Return the seed for a game, or None if game doesn't exist."""
        ...

    @abstractmethod
    def get_game_state(self, game_id: str) -> MahjongGameState | None:
        """Return the current game state, or None if game doesn't exist."""
        ...

    @abstractmethod
    async def handle_timeout(
        self,
        game_id: str,
        player_name: str,
        timeout_type: TimeoutType,
    ) -> list[ServiceEvent]:
        """
        Handle a player timeout by performing the default action.

        For TURN timeout: tsumogiri (discard last drawn tile).
        For MELD timeout: pass on the call opportunity.
        For ROUND_ADVANCE timeout: auto-confirm round advancement.
        """
        ...

    @abstractmethod
    def cleanup_game(self, game_id: str) -> None:
        """
        Remove all game state for a game that was abandoned or cleaned up externally.
        """
        ...

    @abstractmethod
    def replace_with_ai_player(self, game_id: str, player_name: str) -> None:
        """
        Replace a disconnected player with an AI player at their seat.

        Called when a player disconnects mid-game.
        """
        ...

    @abstractmethod
    async def process_ai_player_actions_after_replacement(
        self,
        game_id: str,
        seat: int,
    ) -> list[ServiceEvent]:
        """
        Process pending AI player actions after a player was replaced with an AI player.

        Handles the case where the replaced player had a pending turn or call.
        """
        ...

    @abstractmethod
    def is_round_advance_pending(self, game_id: str) -> bool:
        """Check if a round advance is waiting for player confirmation."""
        ...

    @abstractmethod
    def get_pending_round_advance_player_names(self, game_id: str) -> list[str]:
        """Return player names that still need to confirm round advance."""
        ...
