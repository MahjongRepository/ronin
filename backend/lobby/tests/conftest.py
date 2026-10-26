from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocket

from lobby.players import LobbyPlayer
from lobby.server.app import create_app
from lobby.settings import LobbyServerSettings
from shared.auth.settings import AuthSettings
from shared.websocket import QueuedWebSocket

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator
    from pathlib import Path

    from starlette.applications import Starlette
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

    def send_from_client(self, text: str) -> None:
        self._inbox.put_nowait({"type": "websocket.receive", "text": text})

    def send_bytes_from_client(self, data: bytes) -> None:
        self._inbox.put_nowait({"type": "websocket.receive", "bytes": data})

    def disconnect(self, code: int = 1000) -> None:
        self._inbox.put_nowait({"type": "websocket.disconnect", "code": code})

    def received_json(self) -> list[dict]:
        return [json.loads(m["text"]) for m in self.sent if m["type"] == "websocket.send"]

    def close_codes(self) -> list[int]:
        return [m.get("code", 1000) for m in self.sent if m["type"] == "websocket.close"]


async def nobody_playing(_user_id: str) -> bool:
    return False


class HeldLookup:
    def __init__(self) -> None:
        self.held_user_id: str | None = None
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, user_id: str) -> bool:
        if user_id == self.held_user_id:
            self.started.set()
            await self.release.wait()

        return False


def _refuse_connection(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("no game server in this test", request=request)


class FakeGameServer:
    def __init__(self) -> None:
        self.respond: Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]] = _refuse_connection

    async def handle(self, request: httpx.Request) -> httpx.Response:
        response = self.respond(request)
        if isinstance(response, httpx.Response):
            return response

        return await response


@pytest.fixture
def game_server() -> FakeGameServer:
    return FakeGameServer()


@pytest.fixture
def make_app(tmp_path: Path, game_server: FakeGameServer) -> Callable[..., Starlette]:
    def build(
        *,
        is_playing: Callable[[str], Awaitable[bool]] | None = nobody_playing,
        game_client_dev_transport: httpx.AsyncBaseTransport | None = None,
        **settings_overrides: Any,
    ) -> Starlette:
        static_dir = tmp_path / "public"
        (static_dir / "styles").mkdir(parents=True, exist_ok=True)
        (static_dir / "styles" / "lobby.css").write_text("body { color: red; }")
        return create_app(
            settings=LobbyServerSettings(static_dir=str(static_dir), **settings_overrides),
            auth_settings=AuthSettings(database_path=str(tmp_path / "test.db")),
            is_playing=is_playing,
            game_server_transport=httpx.MockTransport(game_server.handle),
            game_client_dev_transport=game_client_dev_transport,
        )

    return build


@pytest.fixture
def app(make_app: Callable[..., Starlette]) -> Starlette:
    return make_app()


def open_client(app: Starlette) -> TestClient:
    return TestClient(app, headers={"origin": app.state.settings.ws_allowed_origin})


@pytest.fixture
def client(app: Starlette) -> Iterator[TestClient]:
    with open_client(app) as test_client:
        yield test_client


def make_websocket(peer: AsgiPeer, *, app: Starlette, **scope: object) -> WebSocket:
    origin_header = (b"origin", app.state.settings.ws_allowed_origin.encode())
    return WebSocket(
        {"type": "websocket", "path": "/", "headers": [origin_header], "query_string": b"", "app": app, **scope},
        peer.receive,
        peer.send,
    )


def make_player(*, connection_id: str, user_id: str, username: str) -> LobbyPlayer:
    return LobbyPlayer(
        connection_id=connection_id,
        user_id=user_id,
        username=username,
        connection=MagicMock(spec=QueuedWebSocket),
    )
