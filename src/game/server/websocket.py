import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from starlette.websockets import WebSocket, WebSocketDisconnect

from game.messaging.protocol import ConnectionProtocol
from game.messaging.types import ClientMessageType

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

    room_id = websocket.path_params.get("room_id")

    connection = WebSocketConnection(websocket)
    logger.info(f"websocket connected: {connection.connection_id}")
    await router.handle_connect(connection)

    try:
        while True:
            data = await connection.receive_message()
            # inject room ID from URL path into join messages
            if room_id and data.get("type") == ClientMessageType.JOIN_ROOM:
                data["room_id"] = room_id
            await router.handle_message(connection, data)
    except WebSocketDisconnect, RuntimeError:
        pass
    finally:
        logger.info(f"websocket disconnected: {connection.connection_id}")
        await router.handle_disconnect(connection)
