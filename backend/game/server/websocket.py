import contextlib
import re
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from starlette.websockets import WebSocket, WebSocketDisconnect

from game.messaging.encoder import DecodeError, decode
from game.messaging.protocol import ConnectionProtocol
from game.messaging.types import ErrorMessage, SessionErrorCode
from game.server.rate_limit import TokenBucket

logger = structlog.get_logger()

if TYPE_CHECKING:
    from game.messaging.router import MessageRouter

_GAME_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_MAX_GAME_ID_LENGTH = 50

# Rate limit: 50 messages/sec sustained, burst of 80.
# In bot games (1 human + 3 AI), AI turns resolve instantly on the server,
# so a fast client can send ~30 msg/sec (discards + pass on each AI discard).
_RATE_LIMIT_RATE = 50.0
_RATE_LIMIT_BURST = 80

# Disconnect after this many consecutive decode errors
_MAX_DECODE_ERRORS = 5


class WebSocketConnection(ConnectionProtocol):
    def __init__(self, websocket: WebSocket, game_id: str, connection_id: str | None = None) -> None:
        self._websocket = websocket
        self._game_id = game_id
        self._connection_id = connection_id or str(uuid4())

    @property
    def connection_id(self) -> str:
        return self._connection_id

    @property
    def game_id(self) -> str:
        return self._game_id

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
    game_id = websocket.path_params["game_id"]
    if not _GAME_ID_PATTERN.match(game_id) or len(game_id) > _MAX_GAME_ID_LENGTH:
        await websocket.close(code=4000, reason="invalid_game_id")
        return

    await websocket.accept()

    connection = WebSocketConnection(websocket, game_id=game_id)
    logger.info("websocket connected", connection_id=connection.connection_id)
    await router.handle_connect(connection)

    bucket = TokenBucket(rate=_RATE_LIMIT_RATE, burst=_RATE_LIMIT_BURST)
    decode_errors = 0

    try:
        while True:
            raw = await connection.receive_bytes()

            # Always decode to maintain the malformed-message strike counter.
            # Decode is cheap (sub-microsecond for malformed input via the
            # msgpack C extension); the expensive work is in handle_message.
            try:
                data = decode(raw)
            except DecodeError as e:
                decode_errors += 1
                logger.warning("decode error", error=str(e), strikes=decode_errors)
                await connection.send_message(
                    ErrorMessage(code=SessionErrorCode.INVALID_MESSAGE, message=str(e)).model_dump(),
                )
                if decode_errors >= _MAX_DECODE_ERRORS:
                    logger.info(
                        "too many decode errors, disconnecting",
                        connection_id=connection.connection_id,
                    )
                    await connection.close(code=4004, reason="too_many_decode_errors")
                    return
                continue

            decode_errors = 0

            if not bucket.consume():
                await connection.send_message(
                    ErrorMessage(code=SessionErrorCode.RATE_LIMITED, message="Too many messages").model_dump(),
                )
                continue
            await router.handle_message(connection, data)
    except (WebSocketDisconnect, RuntimeError, ConnectionError):  # fmt: skip
        pass
    finally:
        logger.info("websocket disconnected", connection_id=connection.connection_id)
        await router.handle_disconnect(connection)
        structlog.contextvars.clear_contextvars()
