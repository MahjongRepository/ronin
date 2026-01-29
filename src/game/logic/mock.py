from typing import Any

from game.logic.enums import TimeoutType
from game.logic.service import GameService
from game.messaging.events import EventType, GameEvent, ServiceEvent


class MockResultEvent(GameEvent):
    """Mock event for action results in tests."""

    player: str
    action: str
    input: dict[str, Any]
    success: bool


class MockGameStartedEvent(GameEvent):
    """Mock event for game started in tests."""

    seat: int
    player_name: str
    players: list[str]


class MockGameService(GameService):
    """
    Mock game service for testing.

    Simply echoes back actions as events.
    """

    def __init__(self) -> None:
        self._player_seats: dict[str, dict[str, int]] = {}  # game_id -> {player_name -> seat}

    def get_player_seat(self, game_id: str, player_name: str) -> int | None:
        """
        Get the seat number for a player by name.
        """
        game_seats = self._player_seats.get(game_id)
        if game_seats is None:
            return None
        return game_seats.get(player_name)

    async def handle_action(
        self,
        game_id: str,  # noqa: ARG002
        player_name: str,
        action: str,
        data: dict[str, Any],
    ) -> list[ServiceEvent]:
        return [
            ServiceEvent(
                event=f"{action}_result",
                data=MockResultEvent(
                    type=f"{action}_result",
                    target="all",
                    player=player_name,
                    action=action,
                    input=data,
                    success=True,
                ),
                target="all",
            )
        ]

    async def start_game(
        self,
        game_id: str,
        player_names: list[str],
    ) -> list[ServiceEvent]:
        # store player seat assignments (seat 0 for first player)
        self._player_seats[game_id] = {name: i for i, name in enumerate(player_names)}

        # mock returns one event per player with their "view"
        events = []
        for i, name in enumerate(player_names):
            events.append(
                ServiceEvent(
                    event=EventType.GAME_STARTED,
                    data=MockGameStartedEvent(
                        type=EventType.GAME_STARTED,
                        target=f"seat_{i}",
                        seat=i,
                        player_name=name,
                        players=player_names,
                    ),
                    target=f"seat_{i}",
                )
            )
        return events

    async def handle_timeout(
        self,
        game_id: str,  # noqa: ARG002
        player_name: str,
        timeout_type: TimeoutType,
    ) -> list[ServiceEvent]:
        return [
            ServiceEvent(
                event=f"timeout_{timeout_type.value}",
                data=MockResultEvent(
                    type=f"timeout_{timeout_type.value}",
                    target="all",
                    player=player_name,
                    action=f"timeout_{timeout_type.value}",
                    input={},
                    success=True,
                ),
                target="all",
            )
        ]
