from typing import Any

from game.logic.service import GameService


class MockGameService(GameService):
    """
    Mock game service for testing.

    Simply echoes back actions as events.
    """

    async def handle_action(
        self,
        game_id: str,  # noqa: ARG002
        player_name: str,
        action: str,
        data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            {
                "event": f"{action}_result",
                "data": {
                    "player": player_name,
                    "action": action,
                    "input": data,
                    "success": True,
                },
                "target": "all",
            }
        ]

    async def start_game(
        self,
        game_id: str,  # noqa: ARG002
        player_names: list[str],
    ) -> list[dict[str, Any]]:
        # mock returns one event per player with their "view"
        events = []
        for i, name in enumerate(player_names):
            events.append(
                {
                    "event": "game_started",
                    "data": {
                        "seat": i,
                        "player_name": name,
                        "players": player_names,
                    },
                    "target": f"seat_{i}",
                }
            )
        return events
