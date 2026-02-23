"""Unit tests for WebSocketConnection wrapper class."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect

from game.server.websocket import WebSocketConnection


class TestWebSocketConnection:
    """Test error handling and delegation in WebSocketConnection wrapper."""

    async def test_send_bytes_converts_disconnect_to_connection_error(self):
        """Verify that WebSocketDisconnect is converted to ConnectionError on send."""
        mock_ws = MagicMock()
        mock_ws.send_bytes = AsyncMock(side_effect=WebSocketDisconnect())
        conn = WebSocketConnection(mock_ws, game_id="test-game", connection_id="test-conn")

        with pytest.raises(ConnectionError, match="WebSocket already disconnected"):
            await conn.send_bytes(b"data")

    async def test_close_suppresses_disconnect(self):
        """Closing an already-disconnected WebSocket completes without error."""
        mock_ws = MagicMock()
        mock_ws.close = AsyncMock(side_effect=WebSocketDisconnect())
        conn = WebSocketConnection(mock_ws, game_id="test-game", connection_id="test-conn")

        await conn.close()

    async def test_receive_bytes_converts_disconnect_to_connection_error(self):
        """Verify that WebSocketDisconnect is converted to ConnectionError on receive."""
        mock_ws = MagicMock()
        mock_ws.receive_bytes = AsyncMock(side_effect=WebSocketDisconnect())
        conn = WebSocketConnection(mock_ws, game_id="test-game", connection_id="test-conn")

        with pytest.raises(ConnectionError, match="WebSocket already disconnected"):
            await conn.receive_bytes()
