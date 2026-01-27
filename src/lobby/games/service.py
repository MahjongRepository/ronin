import uuid
from typing import TYPE_CHECKING

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

    async def create_game(self) -> CreateGameResponse:
        await self._registry.check_health()
        healthy_servers = self._registry.get_healthy_servers()

        if not healthy_servers:
            raise GameCreationError("No healthy game servers available")

        # for now, just pick the first healthy server
        # future: implement load balancing
        server = healthy_servers[0]

        room_id = str(uuid.uuid4())[:8]

        # request room creation on game server
        await self._create_room_on_server(server, room_id)

        # build WebSocket URL
        ws_url = server.url.replace("http://", "ws://").replace("https://", "wss://")
        websocket_url = f"{ws_url}/ws/{room_id}"

        return CreateGameResponse(
            room_id=room_id,
            websocket_url=websocket_url,
            server_name=server.name,
        )

    async def _create_room_on_server(self, server: GameServer, room_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{server.url}/rooms",
                    json={"room_id": room_id},
                )
                if response.status_code != 201:
                    raise GameCreationError(f"Failed to create room: {response.text}")
            except httpx.RequestError as e:
                raise GameCreationError(f"Failed to connect to game server: {e}") from e
