from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from starlette.websockets import WebSocket

if TYPE_CHECKING:
    from starlette.types import Message


class AsgiPeer:
    def __init__(self) -> None:
        self.sent: list[Message] = []
        self.broken = False
        self.send_gate: asyncio.Event | None = None
        self.send_waiting = asyncio.Event()
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()
        self._inbox.put_nowait({"type": "websocket.connect"})

    async def receive(self) -> Message:
        return await self._inbox.get()

    async def send(self, message: Message) -> None:
        if message["type"] == "websocket.send" and self.send_gate is not None:
            self.send_waiting.set()
            await self.send_gate.wait()

        if self.broken and message["type"] != "websocket.accept":
            raise OSError("broken pipe")

        self.sent.append(message)
        if message["type"] == "websocket.close":
            self._inbox.put_nowait({"type": "websocket.disconnect", "code": message.get("code", 1000)})

    def disconnect(self, code: int = 1000) -> None:
        self._inbox.put_nowait({"type": "websocket.disconnect", "code": code})

    def received_json(self) -> list[dict]:
        return [json.loads(m["text"]) for m in self.sent if m["type"] == "websocket.send"]

    def close_codes(self) -> list[int]:
        return [m.get("code", 1000) for m in self.sent if m["type"] == "websocket.close"]


def make_websocket(peer: AsgiPeer, **scope: object) -> WebSocket:
    return WebSocket(
        {"type": "websocket", "path": "/", "headers": [], "query_string": b"", **scope},
        peer.receive,
        peer.send,
    )


async def open_websocket(peer: AsgiPeer) -> WebSocket:
    websocket = make_websocket(peer)
    await websocket.accept()
    return websocket
