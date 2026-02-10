from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from game.logic.enums import GameAction, TimeoutType

if TYPE_CHECKING:
    from game.logic.events import ServiceEvent
    from game.logic.settings import GameSettings


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
        seed: float | None = None,
        settings: GameSettings | None = None,
    ) -> list[ServiceEvent]:
        """
        Start a game with the given players.

        Returns a list of initial state events (one per player with their view).
        When seed is provided, the game is deterministically reproducible.
        When seed is None, a random seed is generated.
        When settings is provided, the game uses the given settings.
        """
        ...

    @abstractmethod
    def get_player_seat(self, game_id: str, player_name: str) -> int | None:
        """
        Get the seat number for a player by name.
        """
        ...

    @abstractmethod
    def get_game_seed(self, game_id: str) -> float | None:
        """Return the seed for a game, or None if game doesn't exist."""
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
        """
        ...

    @abstractmethod
    def cleanup_game(self, game_id: str) -> None:
        """
        Remove all game state for a game that was abandoned or cleaned up externally.
        """
        ...

    @abstractmethod
    def replace_player_with_bot(self, game_id: str, player_name: str) -> None:
        """
        Replace a human player with a bot at their seat.

        Called when a human disconnects mid-game.
        """
        ...

    @abstractmethod
    async def process_bot_actions_after_replacement(
        self,
        game_id: str,
        seat: int,
    ) -> list[ServiceEvent]:
        """
        Process pending bot actions after a human was replaced with a bot.

        Handles the case where the replaced player had a pending turn or call.
        """
        ...
