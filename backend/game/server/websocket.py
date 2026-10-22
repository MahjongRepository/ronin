import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from starlette.websockets import WebSocket, WebSocketDisconnect

from game.messaging.encoder import DecodeError, decode
from game.messaging.protocol import ConnectionProtocol
from game.messaging.types import ErrorMessage, SessionErrorCode
from game.server.rate_limit import TokenBucket
from shared.tasks import cancel_and_wait

logger = structlog.get_logger()

if TYPE_CHECKING:
    from starlette.types import Message

    from game.server.router import MessageRouter

_GAME_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_MAX_GAME_ID_LENGTH = 50

# Rate limit: 50 messages/sec sustained, burst of 80.
# In bot games (1 human + 3 AI), AI turns resolve instantly on the server,
# so a fast client can send ~30 msg/sec (discards + pass on each AI discard).
_RATE_LIMIT_RATE = 50.0
_RATE_LIMIT_BURST = 80

# Disconnect after this many consecutive decode errors
_MAX_DECODE_ERRORS = 5

_SEND_QUEUE_LIMIT = 256
_SEND_DEADLINE_SECONDS = 10


@dataclass(frozen=True)
class _CloseFrame:
    code: int
    reason: str


class WebSocketConnection(ConnectionProtocol):
    """
    A Starlette WebSocket behind ConnectionProtocol, written by its own writer task.

    Sends and closes go into a bounded queue that the writer drains in order, so no caller waits on the socket. A
    close is the last item: later sends and closes are dropped. A connection the writer cannot serve (the queue is full,
    one send outlasts the send deadline, or the transport reports the peer gone) is terminated: the queue is dropped,
    no close frame is attempted (it could not pass a stalled transport), and `receive_bytes` raises ConnectionError, so
    the endpoint's normal disconnect path runs. Every transport failure of a receive surfaces as ConnectionError too. A
    frame that carries no bytes (a text frame) is client input the protocol cannot decode: DecodeError.
    """

    def __init__(self, websocket: WebSocket, game_id: str, connection_id: str | None = None) -> None:
        self._websocket = websocket
        self._game_id = game_id
        self._connection_id = connection_id or str(uuid4())
        self._queue: asyncio.Queue[bytes | _CloseFrame] = asyncio.Queue(maxsize=_SEND_QUEUE_LIMIT)
        self._close_queued = False
        self._terminated: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._writer: asyncio.Task[None] | None = None

    @property
    def connection_id(self) -> str:
        return self._connection_id

    @property
    def game_id(self) -> str:
        return self._game_id

    def send_bytes(self, data: bytes) -> None:
        self._enqueue(data)

    def close(self, code: int = 1000, reason: str = "") -> None:
        self._enqueue(_CloseFrame(code=code, reason=reason))
        self._close_queued = True

    def _enqueue(self, item: bytes | _CloseFrame) -> None:
        if self._close_queued or self._terminated.done():
            return

        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.warning("websocket send queue full, dropping the connection", connection_id=self._connection_id)
            self._terminate()

    async def receive_bytes(self) -> bytes:
        if self._terminated.done():
            raise ConnectionError("WebSocket terminated")

        receive = asyncio.ensure_future(self._receive_message())
        try:
            await asyncio.wait({receive, self._terminated}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            receive.cancel()
            await asyncio.wait({receive})

        if self._terminated.done():
            raise ConnectionError("WebSocket terminated")

        message = receive.result()
        if message["type"] == "websocket.disconnect":
            raise ConnectionError("WebSocket already disconnected")

        data = message.get("bytes")
        if data is None:
            raise DecodeError("expected a binary MessagePack frame")

        return data

    async def _receive_message(self) -> Message:
        """
        Receive the next ASGI message, a transport failure read as the client's disconnect.
        """
        try:
            return await self._websocket.receive()
        except WebSocketDisconnect, RuntimeError:
            return {"type": "websocket.disconnect"}

    def start_writer(self) -> None:
        """
        Start the task that writes the queue to the socket; the endpoint that accepted the socket owns it.
        """
        self._writer = asyncio.create_task(self._write_queue())

    async def stop_writer(self) -> None:
        """
        Stop the writer, first letting it flush a queued close within the send deadline so the client gets its code.
        """
        if self._writer is None:
            return

        try:
            if self._close_queued and not self._terminated.done():
                await asyncio.wait({self._writer}, timeout=_SEND_DEADLINE_SECONDS)
        finally:
            await cancel_and_wait([self._writer])

    async def _write_queue(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                async with asyncio.timeout(_SEND_DEADLINE_SECONDS):
                    if isinstance(item, _CloseFrame):
                        await self._websocket.close(code=item.code, reason=item.reason)
                        return

                    await self._websocket.send_bytes(item)
            except TimeoutError:
                logger.warning(
                    "websocket send blocked past its deadline, dropping the connection",
                    connection_id=self._connection_id,
                )
                self._terminate()
                return
            except WebSocketDisconnect, RuntimeError:
                logger.info("websocket peer gone, dropping the connection", connection_id=self._connection_id)
                self._terminate()
                return
            except Exception:
                logger.exception("websocket write failed, dropping the connection", connection_id=self._connection_id)
                self._terminate()
                return

    def _terminate(self) -> None:
        """
        Drop a connection the writer cannot serve, synchronously: later sends are no-ops and the receive side ends.
        """
        self._terminated.set_result(None)
        while not self._queue.empty():
            self._queue.get_nowait()

        if self._writer is not None and self._writer is not asyncio.current_task():
            self._writer.cancel()


async def websocket_endpoint(websocket: WebSocket, router: MessageRouter) -> None:
    """
    Serve one game WebSocket; this task owns the connection's writer from accept until the disconnect is handled.
    """
    game_id = websocket.path_params["game_id"]
    if not _GAME_ID_PATTERN.match(game_id) or len(game_id) > _MAX_GAME_ID_LENGTH:
        await websocket.close(code=4000, reason="invalid_game_id")
        return

    await websocket.accept()

    connection = WebSocketConnection(websocket, game_id=game_id)
    connection.start_writer()
    try:
        await _serve_connection(connection, router)
    finally:
        await connection.stop_writer()
        structlog.contextvars.clear_contextvars()


async def _serve_connection(connection: WebSocketConnection, router: MessageRouter) -> None:
    logger.info("websocket connected", connection_id=connection.connection_id)
    router.handle_connect(connection)

    bucket = TokenBucket(rate=_RATE_LIMIT_RATE, burst=_RATE_LIMIT_BURST)
    decode_errors = 0

    try:
        while True:
            # Always decode to maintain the malformed-message strike counter.
            # Decode is cheap (sub-microsecond for malformed input via the
            # msgpack C extension); the expensive work is in handle_message.
            try:
                data = decode(await connection.receive_bytes())
            except DecodeError as e:
                decode_errors += 1
                logger.warning("decode error", error=str(e), strikes=decode_errors)
                connection.send_message(
                    ErrorMessage(code=SessionErrorCode.INVALID_MESSAGE, message=str(e)).model_dump(),
                )
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
                connection.send_message(
                    ErrorMessage(code=SessionErrorCode.RATE_LIMITED, message="Too many messages").model_dump(),
                )
                continue

            await router.handle_message(connection, data)
    except ConnectionError:
        pass
    except Exception:
        logger.exception("websocket message loop failed", connection_id=connection.connection_id)
        connection.close(code=1011, reason="internal_error")
    finally:
        logger.info("websocket disconnected", connection_id=connection.connection_id)
        await router.handle_disconnect(connection)
