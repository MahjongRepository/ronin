import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from starlette.websockets import WebSocket

if TYPE_CHECKING:
    from starlette.types import Message, Scope


@dataclass(frozen=True)
class ClosedWith:
    code: int
    reason: str


class FakeAsgiClient:
    def __init__(self, scope: Scope | None = None) -> None:
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()
        self._inbox.put_nowait({"type": "websocket.connect"})
        self._writable = asyncio.Event()
        self._writable.set()
        self._write_error: Exception | None = None
        self.written_changed = asyncio.Condition()
        self.written: list[object] = []
        self.websocket = WebSocket(
            scope or {"type": "websocket", "path": "/", "headers": []},
            receive=self._inbox.get,
            send=self._receive_from_server,
        )

    def send_frame(self, message: Message) -> None:
        self._inbox.put_nowait(message)

    def disconnect(self) -> None:
        self._inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})

    def hold_writes(self) -> None:
        self._writable.clear()

    def release_writes(self) -> None:
        self._writable.set()

    def fail_writes(self, error: Exception) -> None:
        self._write_error = error

    async def wait_for_close(self) -> ClosedWith:
        async with self.written_changed:
            await self.written_changed.wait_for(lambda: bool(self.written) and isinstance(self.written[-1], ClosedWith))

        closed = self.written[-1]
        assert isinstance(closed, ClosedWith)
        return closed

    def read_frame(self, message: Message) -> object:
        return message["bytes"] if "bytes" in message else message["text"]

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
            self.written.append(self.read_frame(message))

        async with self.written_changed:
            self.written_changed.notify_all()
