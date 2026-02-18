import contextlib
import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from starlette.websockets import WebSocket, WebSocketDisconnect

from game.messaging.encoder import DecodeError
from game.messaging.protocol import ConnectionProtocol
from game.messaging.types import ClientMessageType, ErrorMessage, SessionErrorCode

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
        try:
            return await self._websocket.receive_bytes()
        except WebSocketDisconnect:
            raise ConnectionError("WebSocket already disconnected") from None

    async def close(self, code: int = 1000, reason: str = "") -> None:
        with contextlib.suppress(WebSocketDisconnect):
            await self._websocket.close(code=code, reason=reason)


async def websocket_endpoint(websocket: WebSocket, router: MessageRouter) -> None:
    await websocket.accept()

    room_id = websocket.path_params["room_id"]

    connection = WebSocketConnection(websocket)
    logger.info("websocket connected: %s", connection.connection_id)
    await router.handle_connect(connection)

    try:
        while True:
            try:
                data = await connection.receive_message()
            except DecodeError as e:
                logger.warning("decode error from %s: %s", connection.connection_id, e)
                await connection.send_message(
                    ErrorMessage(code=SessionErrorCode.INVALID_MESSAGE, message=str(e)).model_dump(),
                )
                continue
            if data.get("type") in (ClientMessageType.JOIN_ROOM, ClientMessageType.RECONNECT):
                data["room_id"] = room_id
            await router.handle_message(connection, data)
    except (WebSocketDisconnect, RuntimeError, ConnectionError):  # fmt: skip
        pass
    finally:
        logger.info("websocket disconnected: %s", connection.connection_id)
        await router.handle_disconnect(connection)
