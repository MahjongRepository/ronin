from abc import ABC, abstractmethod
from typing import Any


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
        action: str,
        data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Handle a game action from a player.

        Returns a list of events to broadcast. Each event has:
        - event: str - the event type
        - data: dict - event payload
        - target: str - "all" or "seat_N" for targeted messages
        """
        ...

    @abstractmethod
    async def start_game(
        self,
        game_id: str,
        player_names: list[str],
    ) -> list[dict[str, Any]]:
        """
        Start a game with the given players.

        Returns a list of initial state events (one per player with their view).
        """
        ...
