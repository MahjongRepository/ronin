from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from game.logic.enums import TimeoutType

if TYPE_CHECKING:
    from game.messaging.events import ServiceEvent


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
    ) -> list[ServiceEvent]:
        """
        Start a game with the given players.

        Returns a list of initial state events (one per player with their view).
        """
        ...

    @abstractmethod
    def get_player_seat(self, game_id: str, player_name: str) -> int | None:
        """
        Get the seat number for a player by name.
        """
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
