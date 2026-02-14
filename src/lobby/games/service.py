import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import httpx

from lobby.games.types import CreateRoomResponse

if TYPE_CHECKING:
    from lobby.registry.manager import RegistryManager
    from lobby.registry.types import GameServer


class RoomCreationError(Exception):
    pass


class GamesService:
    def __init__(self, registry: RegistryManager) -> None:
        self._registry = registry

    async def list_rooms(self) -> list[dict[str, Any]]:
        """Fetch rooms from all healthy servers and aggregate."""
        await self._registry.check_health()
        healthy_servers = self._registry.get_healthy_servers()

        all_rooms: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=5.0) as client:
            for server in healthy_servers:
                try:
                    response = await client.get(f"{server.url}/rooms")
                    if response.status_code == HTTPStatus.OK:
                        data = response.json()
                        for room in data.get("rooms", []):
                            room["server_name"] = server.name
                            room["server_url"] = server.url
                            all_rooms.append(room)
                except (httpx.RequestError, ValueError):
                    pass

        return all_rooms

    async def create_room(self, num_ai_players: int = 3) -> CreateRoomResponse:
        await self._registry.check_health()
        healthy_servers = self._registry.get_healthy_servers()

        if not healthy_servers:
            raise RoomCreationError("No healthy game servers available")

        server = healthy_servers[0]
        room_id = str(uuid.uuid4())

        await self._create_room_on_server(server, room_id, num_ai_players)

        ws_url = server.url.replace("http://", "ws://").replace("https://", "wss://")
        websocket_url = f"{ws_url}/ws/{room_id}"

        return CreateRoomResponse(
            room_id=room_id,
            websocket_url=websocket_url,
            server_name=server.name,
        )

    async def _create_room_on_server(self, server: GameServer, room_id: str, num_ai_players: int = 3) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{server.url}/rooms",
                    json={"room_id": room_id, "num_ai_players": num_ai_players},
                )
                if response.status_code != HTTPStatus.CREATED:
                    raise RoomCreationError(f"Failed to create room: {response.text}")
            except httpx.RequestError as e:
                raise RoomCreationError(f"Failed to connect to game server: {e}") from e
