import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import httpx

from lobby.games.types import CreateGameResponse

if TYPE_CHECKING:
    from lobby.registry.manager import RegistryManager
    from lobby.registry.types import GameServer


class GameCreationError(Exception):
    pass


class GamesService:
    def __init__(self, registry: RegistryManager) -> None:
        self._registry = registry

    async def list_games(self) -> list[dict[str, Any]]:
        """
        Fetch games from all healthy servers and aggregate.
        """
        await self._registry.check_health()
        healthy_servers = self._registry.get_healthy_servers()

        all_games: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=5.0) as client:
            for server in healthy_servers:
                try:
                    response = await client.get(f"{server.url}/games")
                    if response.status_code == HTTPStatus.OK:
                        data = response.json()
                        for game in data.get("games", []):
                            game["server_name"] = server.name
                            game["server_url"] = server.url
                            all_games.append(game)
                except (httpx.RequestError, ValueError):
                    # ValueError catches JSON decode errors from non-JSON responses
                    pass

        return all_games

    async def create_game(self) -> CreateGameResponse:
        await self._registry.check_health()
        healthy_servers = self._registry.get_healthy_servers()

        if not healthy_servers:
            raise GameCreationError("No healthy game servers available")

        # for now, just pick the first healthy server
        # future: implement load balancing
        server = healthy_servers[0]

        game_id = str(uuid.uuid4())[:8]

        # request game creation on game server
        await self._create_game_on_server(server, game_id)

        # build WebSocket URL
        ws_url = server.url.replace("http://", "ws://").replace("https://", "wss://")
        websocket_url = f"{ws_url}/ws/{game_id}"

        return CreateGameResponse(
            game_id=game_id,
            websocket_url=websocket_url,
            server_name=server.name,
        )

    async def _create_game_on_server(self, server: GameServer, game_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{server.url}/games",
                    json={"game_id": game_id},
                )
                if response.status_code != HTTPStatus.CREATED:
                    raise GameCreationError(f"Failed to create game: {response.text}")
            except httpx.RequestError as e:
                raise GameCreationError(f"Failed to connect to game server: {e}") from e
