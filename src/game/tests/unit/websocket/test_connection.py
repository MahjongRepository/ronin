"""Unit tests for WebSocketConnection wrapper class."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect

from game.server.websocket import WebSocketConnection


class TestWebSocketConnection:
    """Test error handling and delegation in WebSocketConnection wrapper."""

    async def test_close_delegates_to_underlying_websocket(self):
        """Verify that close() calls the underlying WebSocket's close method."""
        mock_ws = MagicMock()
        mock_ws.close = AsyncMock()
        conn = WebSocketConnection(mock_ws, connection_id="test-conn")

        await conn.close(code=1001, reason="going away")

        mock_ws.close.assert_called_once_with(code=1001, reason="going away")

    async def test_send_bytes_converts_disconnect_to_connection_error(self):
        """Verify that WebSocketDisconnect is converted to ConnectionError on send."""
        mock_ws = MagicMock()
        mock_ws.send_bytes = AsyncMock(side_effect=WebSocketDisconnect())
        conn = WebSocketConnection(mock_ws, connection_id="test-conn")

        with pytest.raises(ConnectionError, match="WebSocket already disconnected"):
            await conn.send_bytes(b"data")

    async def test_close_converts_disconnect_to_connection_error(self):
        """Verify that WebSocketDisconnect is converted to ConnectionError on close."""
        mock_ws = MagicMock()
        mock_ws.close = AsyncMock(side_effect=WebSocketDisconnect())
        conn = WebSocketConnection(mock_ws, connection_id="test-conn")

        with pytest.raises(ConnectionError, match="WebSocket already disconnected"):
            await conn.close()
