from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect

from game.server.websocket import WebSocketConnection


class TestWebSocketConnection:
    @pytest.mark.parametrize("transport_error", [WebSocketDisconnect(), RuntimeError("websocket.send after close")])
    async def test_websocket_connection__when_send_bytes_hits_disconnect__should_raise_connection_error(
        self, transport_error
    ):
        mock_ws = MagicMock()
        mock_ws.send_bytes = AsyncMock(side_effect=transport_error)
        conn = WebSocketConnection(mock_ws, game_id="test-game", connection_id="test-conn")

        with pytest.raises(ConnectionError, match="WebSocket already disconnected"):
            await conn.send_bytes(b"data")

    async def test_websocket_connection__when_close_hits_disconnect__should_suppress_it(self):
        mock_ws = MagicMock()
        mock_ws.close = AsyncMock(side_effect=WebSocketDisconnect())
        conn = WebSocketConnection(mock_ws, game_id="test-game", connection_id="test-conn")

        await conn.close(code=4001, reason="auth_timeout")
        mock_ws.close.assert_awaited_once_with(code=4001, reason="auth_timeout")

    @pytest.mark.parametrize(
        "receive",
        [
            AsyncMock(return_value={"type": "websocket.disconnect", "code": 1006}),
            AsyncMock(side_effect=RuntimeError("receive after disconnect")),
        ],
        ids=["disconnect_message", "runtime_error"],
    )
    async def test_websocket_connection__when_receive_bytes_hits_disconnect__should_raise_connection_error(
        self, receive
    ):
        mock_ws = MagicMock()
        mock_ws.receive = receive
        conn = WebSocketConnection(mock_ws, game_id="test-game", connection_id="test-conn")

        with pytest.raises(ConnectionError, match="WebSocket already disconnected"):
            await conn.receive_bytes()
