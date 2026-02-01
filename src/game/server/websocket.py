import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from starlette.websockets import WebSocket, WebSocketDisconnect

from game.messaging.protocol import ConnectionProtocol

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from game.messaging.router import MessageRouter


class WebSocketConnection(ConnectionProtocol):
    def __init__(self, websocket: WebSocket, connection_id: str | None = None) -> None:
        self._websocket = websocket
        self._connection_id = connection_id or str(uuid4())

    @property
    def connection_id(self) -> str:
        return self._connection_id

    async def send_bytes(self, data: bytes) -> None:
        try:
            await self._websocket.send_bytes(data)
        except WebSocketDisconnect:
            raise ConnectionError("WebSocket already disconnected") from None

    async def receive_bytes(self) -> bytes:
        return await self._websocket.receive_bytes()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        try:
            await self._websocket.close(code=code, reason=reason)
        except WebSocketDisconnect:
            raise ConnectionError("WebSocket already disconnected") from None


async def websocket_endpoint(websocket: WebSocket, router: MessageRouter) -> None:
    await websocket.accept()

    # extract game_id from path if present
    game_id = websocket.path_params.get("game_id")

    connection = WebSocketConnection(websocket)
    logger.info(f"websocket connected: {connection.connection_id}")
    await router.handle_connect(connection)

    try:
        while True:
            data = await connection.receive_message()
            # if game_id is in path, inject it into join_game messages
            if game_id and data.get("type") == "join_game":
                data["game_id"] = game_id
            await router.handle_message(connection, data)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        logger.info(f"websocket disconnected: {connection.connection_id}")
        await router.handle_disconnect(connection)
