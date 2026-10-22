from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from lobby.rooms.connections import RoomConnectionManager
from lobby.tests.conftest import AsgiPeer, open_websocket


def _mock_ws() -> AsyncMock:
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestRoomConnectionManager:
    def test_room_connection_manager_remove__should_return_room_id(self):
        mgr = RoomConnectionManager()
        mgr.add(room_id="room-1", connection_id="conn-1", websocket=_mock_ws())

        result = mgr.remove("conn-1")
        assert result == "room-1"

    def test_room_connection_manager_remove__when_connection_unknown__should_return_none(self):
        mgr = RoomConnectionManager()
        assert mgr.remove("unknown") is None

    def test_room_connection_manager_remove__when_last_connection__should_drop_room(self):
        mgr = RoomConnectionManager()
        mgr.add(room_id="room-1", connection_id="conn-1", websocket=_mock_ws())

        mgr.remove("conn-1")
        # Internal room dict should be cleaned up
        assert "room-1" not in mgr._connections

    @pytest.mark.asyncio
    async def test_room_connection_manager_broadcast__should_send_to_all_connections(self):
        mgr = RoomConnectionManager()
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        mgr.add(room_id="room-1", connection_id="conn-1", websocket=ws1)
        mgr.add(room_id="room-1", connection_id="conn-2", websocket=ws2)

        await mgr.broadcast(room_id="room-1", message={"type": "test"})
        payload = json.dumps({"type": "test"})
        ws1.send_text.assert_called_once_with(payload)
        ws2.send_text.assert_called_once_with(payload)

    @pytest.mark.asyncio
    async def test_room_connection_manager_broadcast__when_exclude_given__should_skip_excluded_connection(self):
        mgr = RoomConnectionManager()
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        mgr.add(room_id="room-1", connection_id="conn-1", websocket=ws1)
        mgr.add(room_id="room-1", connection_id="conn-2", websocket=ws2)

        await mgr.broadcast(room_id="room-1", message={"type": "test"}, exclude="conn-1")
        ws1.send_text.assert_not_called()
        ws2.send_text.assert_called_once()

    async def test_room_connection_manager_broadcast__when_earlier_peer_is_dead__should_still_reach_later_peers(self):
        mgr = RoomConnectionManager()
        dead_peer = AsgiPeer()
        healthy_peer = AsgiPeer()
        mgr.add(room_id="room-1", connection_id="dead", websocket=await open_websocket(dead_peer))
        mgr.add(room_id="room-1", connection_id="healthy", websocket=await open_websocket(healthy_peer))
        dead_peer.broken = True

        await mgr.broadcast(room_id="room-1", message={"type": "test"})
        assert healthy_peer.received_json() == [{"type": "test"}]

    @pytest.mark.asyncio
    async def test_room_connection_manager_broadcast__when_room_unknown__should_not_raise(self):
        mgr = RoomConnectionManager()
        # Should not raise
        await mgr.broadcast(room_id="nonexistent", message={"type": "test"})

    @pytest.mark.asyncio
    async def test_room_connection_manager_send_to__should_send_json_to_connection(self):
        mgr = RoomConnectionManager()
        ws = _mock_ws()
        mgr.add(room_id="room-1", connection_id="conn-1", websocket=ws)

        sent = await mgr.send_to("conn-1", {"type": "hello"})
        assert sent is True
        ws.send_text.assert_called_once_with(json.dumps({"type": "hello"}))

    @pytest.mark.asyncio
    async def test_room_connection_manager_send_to__when_connection_unknown__should_return_false(self):
        mgr = RoomConnectionManager()
        assert await mgr.send_to("unknown", {"type": "test"}) is False

    @pytest.mark.asyncio
    async def test_room_connection_manager_send_to__when_socket_missing_from_room__should_not_send(self):
        mgr = RoomConnectionManager()
        ws = _mock_ws()
        mgr.add(room_id="room-1", connection_id="conn-1", websocket=ws)
        # Remove ws from internal connections but keep reverse mapping
        mgr._connections["room-1"].pop("conn-1")

        # Should not raise
        await mgr.send_to("conn-1", {"type": "test"})
        ws.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_room_connection_manager_close_connections__should_close_all_and_drop_room(self):
        mgr = RoomConnectionManager()
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        mgr.add(room_id="room-1", connection_id="conn-1", websocket=ws1)
        mgr.add(room_id="room-1", connection_id="conn-2", websocket=ws2)

        await mgr.close_connections(room_id="room-1", code=4002, reason="expired")
        ws1.close.assert_called_once_with(code=4002, reason="expired")
        ws2.close.assert_called_once_with(code=4002, reason="expired")
        assert "room-1" not in mgr._connections

    async def test_room_connection_manager_close_connections__when_a_peer_is_dead__should_close_and_unindex_all(self):
        mgr = RoomConnectionManager()
        dead_peer = AsgiPeer()
        healthy_peer = AsgiPeer()
        mgr.add(room_id="room-1", connection_id="dead", websocket=await open_websocket(dead_peer))
        mgr.add(room_id="room-1", connection_id="healthy", websocket=await open_websocket(healthy_peer))
        dead_peer.broken = True

        await mgr.close_connections(room_id="room-1", code=4002, reason="room_expired")
        assert healthy_peer.close_codes() == [4002]
        assert mgr.remove("dead") is None
        assert mgr.remove("healthy") is None

    @pytest.mark.asyncio
    async def test_room_connection_manager_close_connections__when_room_unknown__should_not_raise(self):
        mgr = RoomConnectionManager()
        # Should not raise
        await mgr.close_connections(room_id="nonexistent")
