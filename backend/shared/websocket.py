import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog
from starlette.websockets import WebSocket, WebSocketDisconnect

from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    from starlette.types import Message

logger = structlog.get_logger()

_SEND_QUEUE_LIMIT = 256
_SEND_DEADLINE_SECONDS = 10


@dataclass(frozen=True)
class _CloseFrame:
    code: int
    reason: str


class QueuedWebSocket:
    """
    An accepted Starlette WebSocket written by its own writer task, so no caller waits on the socket.

    Sends and closes go into a bounded queue that the writer drains in order. A close is the last item: later sends and
    closes are dropped, as is everything enqueued once the writer is stopped. A connection the writer cannot serve (the
    queue is full, one send outlasts the send deadline, or the transport reports the peer gone) is terminated: the queue
    is dropped, no close frame is attempted (it could not pass a stalled transport), and `receive` raises
    ConnectionError, so the endpoint's normal disconnect path runs. Every transport failure of a receive surfaces as
    ConnectionError too.
    """

    def __init__(self, websocket: WebSocket, *, connection_id: str) -> None:
        self._websocket = websocket
        self._connection_id = connection_id
        self._queue: asyncio.Queue[bytes | str | _CloseFrame] = asyncio.Queue(maxsize=_SEND_QUEUE_LIMIT)
        self._closed = False
        self._terminated: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._writer: asyncio.Task[None] | None = None

    def send_bytes(self, data: bytes) -> None:
        self._enqueue(data)

    def send_text(self, data: str) -> None:
        self._enqueue(data)

    def close(self, code: int = 1000, reason: str = "") -> None:
        self._enqueue(_CloseFrame(code=code, reason=reason))
        self._closed = True

    def _enqueue(self, item: bytes | str | _CloseFrame) -> None:
        if self._closed or self._terminated.done():
            return

        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.warning("websocket send queue full, dropping the connection", connection_id=self._connection_id)
            self._terminate()

    async def receive(self) -> Message:
        """
        Receive the client's next ASGI ``websocket.receive`` message; raise ConnectionError once the socket is gone.
        """
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

        return message

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

        Later sends and closes are dropped: nobody would write them.
        """
        if self._writer is None:
            return

        try:
            if self._closed and not self._terminated.done():
                await asyncio.wait({self._writer}, timeout=_SEND_DEADLINE_SECONDS)
        finally:
            self._closed = True
            await cancel_and_wait([self._writer])

    async def _write_queue(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                async with asyncio.timeout(_SEND_DEADLINE_SECONDS):
                    if isinstance(item, _CloseFrame):
                        await self._websocket.close(code=item.code, reason=item.reason)
                        return

                    if isinstance(item, str):
                        await self._websocket.send_text(item)
                    else:
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


async def reject_websocket(websocket: WebSocket, *, code: int, reason: str) -> None:
    """
    Close a socket before accepting it; a peer already gone (the ASGI server raises OSError) ends it quietly.
    """
    try:
        await websocket.close(code=code, reason=reason)
    except OSError:
        logger.info("websocket peer gone before its rejection", code=code, reason=reason)


async def accept_websocket(websocket: WebSocket) -> bool:
    """
    Accept a socket; return False when the peer is already gone (the ASGI server raises OSError).
    """
    try:
        await websocket.accept()
    except OSError:
        logger.info("websocket peer gone before its accept")
        return False

    return True
