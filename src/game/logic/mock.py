from typing import Any

from game.logic.service import GameService


class MockGameService(GameService):
    """Mock game service for testing.

    Simply echoes back actions as events.
    """

    async def handle_action(
        self,
        game_id: str,  # noqa: ARG002
        player_name: str,
        action: str,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        return {
            "event": f"{action}_result",
            "data": {
                "player": player_name,
                "action": action,
                "input": data,
                "success": True,
            },
        }
