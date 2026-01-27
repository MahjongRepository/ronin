import asyncio
from typing import Any
from uuid import uuid4

from game.messaging.protocol import ConnectionProtocol


class MockConnection(ConnectionProtocol):
    def __init__(self, connection_id: str | None = None) -> None:
        self._connection_id = connection_id or str(uuid4())
        self._inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._outbox: list[dict[str, Any]] = []
        self._closed = False
        self._close_code: int | None = None
        self._close_reason: str | None = None

    @property
    def connection_id(self) -> str:
        return self._connection_id

    @property
    def sent_messages(self) -> list[dict[str, Any]]:
        return self._outbox.copy()

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def send_json(self, data: dict[str, Any]) -> None:
        if self._closed:
            raise RuntimeError("Connection is closed")
        self._outbox.append(data)

    async def receive_json(self) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("Connection is closed")
        return await self._inbox.get()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self._closed = True
        self._close_code = code
        self._close_reason = reason

    async def simulate_receive(self, data: dict[str, Any]) -> None:
        await self._inbox.put(data)

    def simulate_receive_nowait(self, data: dict[str, Any]) -> None:
        self._inbox.put_nowait(data)
