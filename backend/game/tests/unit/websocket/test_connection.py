from unittest.mock import AsyncMock, MagicMock

import pytest

from game.server import websocket as ws_module
from game.server.websocket import WebSocketConnection
from game.tests.helpers.fake_websocket import ClosedWith, FakeWebSocketClient


class TestWebSocketConnection:
    async def test_websocket_connection__when_closed_after_sends__should_write_them_in_order_and_drop_what_follows(
        self,
    ):
        client = FakeWebSocketClient()
        conn = WebSocketConnection(client.websocket, game_id="game1")
        await client.websocket.accept()
        conn.start_writer()

        conn.send_message({"n": 1})
        conn.send_message({"n": 2})
        conn.close(code=1000, reason="game_ended")
        conn.send_message({"n": 3})
        conn.close(code=1011, reason="internal_error")
        await conn.stop_writer()
        assert client.written == [{"n": 1}, {"n": 2}, ClosedWith(code=1000, reason="game_ended")]

    @pytest.mark.parametrize(
        "transport_error",
        [
            OSError("client gone"),
            RuntimeError("Unexpected ASGI message 'websocket.send' after 'websocket.close'"),
            ValueError("unexpected transport fault"),
        ],
        ids=["disconnect", "runtime_error", "unexpected_error"],
    )
    async def test_websocket_connection__when_a_write_fails__should_end_receive(self, transport_error):
        client = FakeWebSocketClient()
        conn = WebSocketConnection(client.websocket, game_id="game1")
        await client.websocket.accept()
        client.fail_writes(transport_error)
        conn.start_writer()

        conn.send_message({"n": 1})
        with pytest.raises(ConnectionError, match="WebSocket terminated"):
            await conn.receive_bytes()
        conn.send_message({"n": 2})
        conn.close()
        await conn.stop_writer()
        assert client.written == []

    async def test_websocket_connection__when_a_send_outlasts_its_deadline__should_terminate_without_a_close_frame(
        self, monkeypatch
    ):
        monkeypatch.setattr(ws_module, "_SEND_DEADLINE_SECONDS", 0.01)
        client = FakeWebSocketClient()
        conn = WebSocketConnection(client.websocket, game_id="game1")
        await client.websocket.accept()
        client.hold_writes()
        conn.start_writer()

        conn.send_message({"n": 1})
        conn.close(code=1000, reason="game_ended")
        with pytest.raises(ConnectionError, match="WebSocket terminated"):
            await conn.receive_bytes()
        client.release_writes()
        await conn.stop_writer()
        assert client.written == []

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
