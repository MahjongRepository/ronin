from typing import Any

from game.logic.enums import TimeoutType
from game.logic.service import GameService
from game.logic.types import GamePlayerInfo, GameView, PlayerView
from game.messaging.events import EventType, GameEvent, GameStartedEvent, RoundStartedEvent, ServiceEvent


class MockResultEvent(GameEvent):
    """Mock event for action results in tests."""

    player: str
    action: str
    input: dict[str, Any]
    success: bool


class MockGameService(GameService):
    """Mock game service for testing.

    Simply echoes back actions as events.
    """

    def __init__(self) -> None:
        self._player_seats: dict[str, dict[str, int]] = {}  # game_id -> {player_name -> seat}

    def get_player_seat(self, game_id: str, player_name: str) -> int | None:
        """Get the seat number for a player by name."""
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

        all_names = player_names + ["Bot"] * (4 - len(player_names))
        human_count = len(player_names)

        mock_view = GameView(
            seat=0,
            round_wind="East",
            round_number=0,
            dealer_seat=0,
            current_player_seat=0,
            wall_count=70,
            dora_indicators=[],
            honba_sticks=0,
            riichi_sticks=0,
            players=[
                PlayerView(
                    seat=i,
                    name=name,
                    is_bot=i >= human_count,
                    score=25000,
                    is_riichi=False,
                    discards=[],
                    melds=[],
                    tile_count=13,
                )
                for i, name in enumerate(all_names)
            ],
            phase="playing",
            game_phase="playing",
        )

        players = [
            GamePlayerInfo(seat=i, name=name, is_bot=i >= human_count) for i, name in enumerate(all_names)
        ]

        return [
            ServiceEvent(
                event=EventType.GAME_STARTED,
                data=GameStartedEvent(game_id=game_id, players=players),
                target="all",
            ),
            ServiceEvent(
                event=EventType.ROUND_STARTED,
                data=RoundStartedEvent(
                    view=mock_view,
                    target="seat_0",
                ),
                target="seat_0",
            ),
        ]

    def cleanup_game(self, game_id: str) -> None:
        self._player_seats.pop(game_id, None)

    def replace_player_with_bot(
        self,
        game_id: str,
        player_name: str,
    ) -> None:
        pass

    async def process_bot_actions_after_replacement(
        self,
        game_id: str,  # noqa: ARG002
        seat: int,  # noqa: ARG002
    ) -> list[ServiceEvent]:
        return []

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
