import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from starlette.websockets import WebSocket

from game.messaging.encoder import decode, encode

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.types import Message


@dataclass(frozen=True)
class ClosedWith:
    code: int
    reason: str


class FakeWebSocketClient:
    """
    The client side of a real Starlette WebSocket, speaking ASGI to it the way uvicorn does.

    Writes from the server pass only while the client is writable: `hold_writes` makes them wait, as uvicorn's send
    waits on a paused transport, and `fail_writes` makes them raise (uvicorn raises OSError for a peer that is gone).
    A close the server sends is answered with the client's disconnect.
    """

    def __init__(self, game_id: str = "game1") -> None:
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()
        self._inbox.put_nowait({"type": "websocket.connect"})
        self._writable = asyncio.Event()
        self._writable.set()
        self._write_error: Exception | None = None
        self._written_changed = asyncio.Condition()
        self.written: list[dict[str, Any] | ClosedWith] = []
        self.websocket = WebSocket(
            {"type": "websocket", "path": f"/ws/{game_id}", "path_params": {"game_id": game_id}, "headers": []},
            receive=self._inbox.get,
            send=self._receive_from_server,
        )

    @property
    def messages(self) -> list[dict[str, Any]]:
        return [item for item in self.written if isinstance(item, dict)]

    def send(self, data: dict[str, Any]) -> None:
        self._inbox.put_nowait({"type": "websocket.receive", "bytes": encode(data)})

    def disconnect(self) -> None:
        self._inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})

    def hold_writes(self) -> None:
        self._writable.clear()

    def release_writes(self) -> None:
        self._writable.set()

    def fail_writes(self, error: Exception) -> None:
        self._write_error = error

    async def wait_for_message(self, predicate: Callable[[dict[str, Any]], bool]) -> None:
        async with self._written_changed:
            await self._written_changed.wait_for(lambda: any(predicate(message) for message in self.messages))

    async def wait_for_close(self) -> ClosedWith:
        async with self._written_changed:
            await self._written_changed.wait_for(
                lambda: bool(self.written) and isinstance(self.written[-1], ClosedWith)
            )

        closed = self.written[-1]
        assert isinstance(closed, ClosedWith)
        return closed

    async def _receive_from_server(self, message: Message) -> None:
        if message["type"] == "websocket.accept":
            return

        await self._writable.wait()
        if self._write_error is not None:
            raise self._write_error

        if message["type"] == "websocket.close":
            self.written.append(ClosedWith(code=message["code"], reason=message.get("reason") or ""))
            self._inbox.put_nowait({"type": "websocket.disconnect", "code": message["code"]})
        else:
            self.written.append(decode(message["bytes"]))

        async with self._written_changed:
            self._written_changed.notify_all()
