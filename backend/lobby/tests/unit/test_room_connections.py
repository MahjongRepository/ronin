"""Tests for RoomConnectionManager."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from lobby.rooms.connections import RoomConnectionManager


def _mock_ws() -> AsyncMock:
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestRoomConnectionManager:
    def test_add_connection(self):
        mgr = RoomConnectionManager()
        ws = _mock_ws()
        mgr.add("room-1", "conn-1", ws)
        assert "room-1" in mgr._connections
        assert "conn-1" in mgr._connections["room-1"]

    def test_remove_returns_room_id(self):
        mgr = RoomConnectionManager()
        mgr.add("room-1", "conn-1", _mock_ws())
        result = mgr.remove("conn-1")
        assert result == "room-1"

    def test_remove_unknown_returns_none(self):
        mgr = RoomConnectionManager()
        assert mgr.remove("unknown") is None

    def test_remove_cleans_up_empty_room(self):
        mgr = RoomConnectionManager()
        mgr.add("room-1", "conn-1", _mock_ws())
        mgr.remove("conn-1")
        # Internal room dict should be cleaned up
        assert "room-1" not in mgr._connections

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self):
        mgr = RoomConnectionManager()
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        mgr.add("room-1", "conn-1", ws1)
        mgr.add("room-1", "conn-2", ws2)

        await mgr.broadcast("room-1", {"type": "test"})

        payload = json.dumps({"type": "test"})
        ws1.send_text.assert_called_once_with(payload)
        ws2.send_text.assert_called_once_with(payload)

    @pytest.mark.asyncio
    async def test_broadcast_with_exclude(self):
        mgr = RoomConnectionManager()
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        mgr.add("room-1", "conn-1", ws1)
        mgr.add("room-1", "conn-2", ws2)

        await mgr.broadcast("room-1", {"type": "test"}, exclude="conn-1")

        ws1.send_text.assert_not_called()
        ws2.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_suppresses_connection_error(self):
        mgr = RoomConnectionManager()
        ws1 = _mock_ws()
        ws1.send_text.side_effect = ConnectionError("broken pipe")
        ws2 = _mock_ws()
        mgr.add("room-1", "conn-1", ws1)
        mgr.add("room-1", "conn-2", ws2)

        await mgr.broadcast("room-1", {"type": "test"})

        # ws2 should still receive the message despite ws1 failing
        ws2.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_empty_room(self):
        mgr = RoomConnectionManager()
        # Should not raise
        await mgr.broadcast("nonexistent", {"type": "test"})

    @pytest.mark.asyncio
    async def test_send_to_specific_connection(self):
        mgr = RoomConnectionManager()
        ws = _mock_ws()
        mgr.add("room-1", "conn-1", ws)

        await mgr.send_to("conn-1", {"type": "hello"})

        ws.send_text.assert_called_once_with(json.dumps({"type": "hello"}))

    @pytest.mark.asyncio
    async def test_send_to_unknown_connection(self):
        mgr = RoomConnectionManager()
        # Should not raise
        await mgr.send_to("unknown", {"type": "test"})

    @pytest.mark.asyncio
    async def test_send_to_suppresses_error(self):
        mgr = RoomConnectionManager()
        ws = _mock_ws()
        ws.send_text.side_effect = RuntimeError("closed")
        mgr.add("room-1", "conn-1", ws)

        # Should not raise
        await mgr.send_to("conn-1", {"type": "test"})

    @pytest.mark.asyncio
    async def test_close_connections(self):
        mgr = RoomConnectionManager()
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        mgr.add("room-1", "conn-1", ws1)
        mgr.add("room-1", "conn-2", ws2)

        await mgr.close_connections("room-1", code=4002, reason="expired")

        ws1.close.assert_called_once_with(code=4002, reason="expired")
        ws2.close.assert_called_once_with(code=4002, reason="expired")
        assert "room-1" not in mgr._connections

    @pytest.mark.asyncio
    async def test_close_connections_suppresses_error(self):
        mgr = RoomConnectionManager()
        ws = _mock_ws()
        ws.close.side_effect = RuntimeError("already closed")
        mgr.add("room-1", "conn-1", ws)

        # Should not raise
        await mgr.close_connections("room-1")

    @pytest.mark.asyncio
    async def test_close_connections_empty_room(self):
        mgr = RoomConnectionManager()
        # Should not raise
        await mgr.close_connections("nonexistent")

    @pytest.mark.asyncio
    async def test_send_to_ws_missing_from_room(self):
        """send_to when connection is tracked but ws was removed from _connections."""
        mgr = RoomConnectionManager()
        ws = _mock_ws()
        mgr.add("room-1", "conn-1", ws)
        # Remove ws from internal connections but keep reverse mapping
        mgr._connections["room-1"].pop("conn-1")
        # Should not raise
        await mgr.send_to("conn-1", {"type": "test"})
        ws.send_text.assert_not_called()
