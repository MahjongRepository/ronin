from abc import ABC, abstractmethod
from typing import Any


class GameService(ABC):
    """Abstract interface for game logic.

    This will be implemented with real Riichi Mahjong rules later.
    For now, we use a mock implementation for testing.
    """

    @abstractmethod
    async def handle_action(
        self,
        room_id: str,
        player_name: str,
        action: str,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Handle a game action from a player.

        Returns an event dict to broadcast, or None if no broadcast needed.
        """
        ...
