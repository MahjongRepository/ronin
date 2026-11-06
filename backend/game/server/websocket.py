import re
import time
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog

from game.messaging.encoder import DecodeError, decode
from game.messaging.protocol import ConnectionProtocol
from game.messaging.types import ErrorMessage, SessionErrorCode, refused_wait_id
from game.messaging.wire_enums import WireClientMessageType
from game.wire.keys import WireKey
from shared.rate_limit import TokenBucket
from shared.websocket import QueuedWebSocket, accept_websocket, reject_websocket

logger = structlog.get_logger()

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

    from game.server.router import MessageRouter
    from game.server.socket_stats import SocketStats

_GAME_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_MAX_GAME_ID_LENGTH = 50

# Rate limit: 50 messages/sec sustained, burst of 80.
_RATE_LIMIT_RATE = 50.0
_RATE_LIMIT_BURST = 80

_RESYNC_RATE_LIMIT_RATE = 0.2
_RESYNC_RATE_LIMIT_BURST = 2

# Disconnect after this many consecutive decode errors
_MAX_DECODE_ERRORS = 5


class WebSocketConnection(ConnectionProtocol):
    """
    A game's Starlette WebSocket behind ConnectionProtocol, its sends and closes queued for its writer task.

    The transport (the bounded queue, the send deadline, termination and receive) is `QueuedWebSocket`'s. A frame that
    carries no bytes (a text frame) is client input the protocol cannot decode: DecodeError.
    """

    def __init__(
        self,
        websocket: WebSocket,
        game_id: str,
        *,
        socket_stats: SocketStats,
        connection_id: str | None = None,
    ) -> None:
        self._game_id = game_id
        self._socket_stats = socket_stats
        self._connection_id = connection_id or str(uuid4())
        self._socket = QueuedWebSocket(websocket, connection_id=self._connection_id)

    @property
    def connection_id(self) -> str:
        return self._connection_id

    @property
    def game_id(self) -> str:
        return self._game_id

    @property
    def disconnect_code(self) -> int | None:
        return self._socket.disconnect_code

    def send_bytes(self, data: bytes) -> None:
        self._socket_stats.messages_out += 1
        self._socket_stats.bytes_out += len(data)
        self._socket.send_bytes(data)

    def close(self, code: int = 1000, reason: str = "") -> None:
        self._socket_stats.count_close(code)
        self._socket.close(code=code, reason=reason)

    async def receive_bytes(self) -> bytes:
        message = await self._socket.receive()
        data = message.get("bytes")
        if data is None:
            raise DecodeError("expected a binary MessagePack frame")

        return data

    def start_writer(self) -> None:
        self._socket.start_writer()

    async def stop_writer(self) -> None:
        await self._socket.stop_writer()


async def websocket_endpoint(websocket: WebSocket, router: MessageRouter) -> None:
    """
    Serve one game WebSocket; this task owns the connection's writer from accept until the disconnect is handled.
    """
    game_id = websocket.path_params["game_id"]
    if not _GAME_ID_PATTERN.match(game_id) or len(game_id) > _MAX_GAME_ID_LENGTH:
        await reject_websocket(websocket, code=4000, reason="invalid_game_id")
        return

    if not await accept_websocket(websocket):
        return

    socket_stats = router.socket_stats
    socket_stats.connections_accepted += 1
    socket_stats.connections += 1
    connection = WebSocketConnection(websocket, game_id=game_id, socket_stats=socket_stats)
    connection.start_writer()
    try:
        await _serve_connection(connection, router)
    finally:
        socket_stats.connections -= 1
        await connection.stop_writer()
        structlog.contextvars.clear_contextvars()


async def _serve_connection(connection: WebSocketConnection, router: MessageRouter) -> None:
    logger.info("websocket connected", connection_id=connection.connection_id)
    router.handle_connect(connection)

    socket_stats = router.socket_stats
    bucket = TokenBucket(rate=_RATE_LIMIT_RATE, burst=_RATE_LIMIT_BURST)
    resync_bucket = TokenBucket(rate=_RESYNC_RATE_LIMIT_RATE, burst=_RESYNC_RATE_LIMIT_BURST)
    decode_errors = 0

    try:
        while True:
            # Always decode to maintain the malformed-message strike counter.
            # Decode is cheap (sub-microsecond for malformed input via the
            # msgpack C extension); the expensive work is in handle_message.
            try:
                frame = await connection.receive_bytes()
                received_at = time.perf_counter()
                socket_stats.messages_in += 1
                socket_stats.bytes_in += len(frame)
                data = decode(frame)
            except DecodeError as e:
                socket_stats.malformed_messages += 1
                decode_errors += 1
                if bucket.consume():
                    logger.warning("decode error", error=str(e), strikes=decode_errors)
                    connection.send_message(
                        ErrorMessage(code=SessionErrorCode.INVALID_MESSAGE, message=str(e)).payload(),
                    )
                else:
                    socket_stats.rate_limited_messages += 1

                if decode_errors >= _MAX_DECODE_ERRORS:
                    logger.info(
                        "too many decode errors, disconnecting",
                        connection_id=connection.connection_id,
                    )
                    connection.close(code=4004, reason="too_many_decode_errors")
                    return

                continue

            decode_errors = 0

            if not bucket.consume():
                socket_stats.rate_limited_messages += 1
                connection.send_message(
                    ErrorMessage(
                        code=SessionErrorCode.RATE_LIMITED,
                        message="Too many messages",
                        wait_id=refused_wait_id(data),
                    ).payload(),
                )
                continue

            if data.get(WireKey.EVENT_TYPE) == WireClientMessageType.RESYNC and not resync_bucket.consume():
                socket_stats.rate_limited_messages += 1
                connection.send_message(
                    ErrorMessage(code=SessionErrorCode.RATE_LIMITED, message="Too many resync requests").payload(),
                )
                continue

            router.handle_message(connection, data)
            socket_stats.handling_seconds += time.perf_counter() - received_at
            socket_stats.handled_messages += 1
    except ConnectionError:
        pass
    except Exception:
        logger.exception("websocket message loop failed", connection_id=connection.connection_id)
        connection.close(code=1011, reason="internal_error")
    finally:
        logger.info(
            "websocket disconnected", connection_id=connection.connection_id, close_code=connection.disconnect_code
        )
        router.handle_disconnect(connection)
