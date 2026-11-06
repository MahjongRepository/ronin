import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocket

from shared import websocket as shared_websocket
from shared.tests.helpers.fake_websocket import ClosedWith, FakeAsgiClient
from shared.websocket import QueuedWebSocket, accept_websocket, reject_websocket


async def _open_queued_websocket(client: FakeAsgiClient) -> QueuedWebSocket:
    await client.websocket.accept()
    return QueuedWebSocket(client.websocket, connection_id="conn1")


async def _wait_until_written(client: FakeAsgiClient, expected: list[object]) -> None:
    async with client.written_changed:
        await client.written_changed.wait_for(lambda: client.written == expected)


class TestQueuedWebSocket:
    async def test_queued_websocket__when_closed_after_sends__should_write_them_in_order_and_drop_what_follows(self):
        client = FakeAsgiClient()
        socket = await _open_queued_websocket(client)
        socket.start_writer()

        socket.send_bytes(b"1")
        socket.send_text("2")
        socket.close(code=1000, reason="game_ended")
        socket.send_bytes(b"3")
        socket.close(code=1011, reason="internal_error")
        await socket.stop_writer()
        assert client.written == [b"1", "2", ClosedWith(code=1000, reason="game_ended")]

    @pytest.mark.parametrize(
        "transport_error",
        [
            OSError("client gone"),
            RuntimeError("Unexpected ASGI message 'websocket.send' after 'websocket.close'"),
            ValueError("unexpected transport fault"),
        ],
        ids=["disconnect", "runtime_error", "unexpected_error"],
    )
    async def test_queued_websocket__when_a_write_fails__should_end_receive(self, transport_error):
        client = FakeAsgiClient()
        socket = await _open_queued_websocket(client)
        client.fail_writes(transport_error)
        socket.start_writer()

        socket.send_bytes(b"1")
        with pytest.raises(ConnectionError, match="WebSocket terminated"):
            await socket.receive()
        socket.send_bytes(b"2")
        socket.close()
        await socket.stop_writer()
        assert client.written == []

    async def test_queued_websocket__when_its_queue_overflows_with_input_buffered__should_end_receive(
        self, monkeypatch
    ):
        monkeypatch.setattr(shared_websocket, "_SEND_QUEUE_LIMIT", 1)
        client = FakeAsgiClient()
        socket = await _open_queued_websocket(client)
        socket.start_writer()
        client.send_frame({"type": "websocket.receive", "bytes": b"buffered"})

        socket.send_bytes(b"1")
        socket.send_bytes(b"2")
        socket._terminate()
        with pytest.raises(ConnectionError, match="WebSocket terminated"):
            await socket.receive()
        await socket.stop_writer()
        assert client.written == []

    async def test_queued_websocket__when_a_send_outlasts_its_deadline__should_terminate_without_a_close_frame(
        self, monkeypatch
    ):
        monkeypatch.setattr(shared_websocket, "_SEND_DEADLINE_SECONDS", 0.01)
        client = FakeAsgiClient()
        socket = await _open_queued_websocket(client)
        client.hold_writes()
        socket.start_writer()

        socket.send_bytes(b"1")
        socket.close(code=1000, reason="game_ended")
        with pytest.raises(ConnectionError, match="WebSocket terminated"):
            await socket.receive()
        client.release_writes()
        await socket.stop_writer()
        assert client.written == []

    async def test_queued_websocket__when_a_slow_send_follows_a_fast_one__should_give_it_its_own_full_deadline(
        self, monkeypatch
    ):
        deadline = 0.05
        monkeypatch.setattr(shared_websocket, "_SEND_DEADLINE_SECONDS", deadline)
        loop = asyncio.get_running_loop()
        client = FakeAsgiClient()
        socket = await _open_queued_websocket(client)
        socket.start_writer()

        socket.send_bytes(b"1")
        await _wait_until_written(client, [b"1"])
        await asyncio.sleep(deadline / 2)
        client.hold_writes()
        slow_send_queued_at = loop.time()
        socket.send_bytes(b"2")
        with pytest.raises(ConnectionError, match="WebSocket terminated"):
            await socket.receive()
        assert loop.time() >= slow_send_queued_at + deadline
        client.release_writes()
        await socket.stop_writer()
        assert client.written == [b"1"]

    async def test_queued_websocket__when_idle_past_the_deadline_after_a_send__should_stay_open_and_send_again(
        self, monkeypatch
    ):
        deadline = 0.01
        monkeypatch.setattr(shared_websocket, "_SEND_DEADLINE_SECONDS", deadline)
        client = FakeAsgiClient()
        socket = await _open_queued_websocket(client)
        socket.start_writer()

        socket.send_bytes(b"1")
        await _wait_until_written(client, [b"1"])
        await asyncio.sleep(deadline * 3)
        socket.send_bytes(b"2")
        await _wait_until_written(client, [b"1", b"2"])
        client.send_frame({"type": "websocket.receive", "bytes": b"still open"})
        assert await socket.receive() == {"type": "websocket.receive", "bytes": b"still open"}
        await socket.stop_writer()

    @pytest.mark.parametrize(
        "receive",
        [
            AsyncMock(return_value={"type": "websocket.disconnect", "code": 1006}),
            AsyncMock(side_effect=RuntimeError("receive after disconnect")),
        ],
        ids=["disconnect_message", "runtime_error"],
    )
    async def test_queued_websocket__when_receive_hits_disconnect__should_raise_connection_error(self, receive):
        mock_ws = MagicMock()
        mock_ws.receive = receive
        socket = QueuedWebSocket(mock_ws, connection_id="test-conn")

        with pytest.raises(ConnectionError, match="WebSocket already disconnected"):
            await socket.receive()

    async def test_queued_websocket__when_its_writer_stopped__should_drop_later_sends(self, monkeypatch, caplog):
        monkeypatch.setattr(shared_websocket, "_SEND_QUEUE_LIMIT", 1)
        client = FakeAsgiClient()
        socket = await _open_queued_websocket(client)
        socket.start_writer()
        await socket.stop_writer()

        socket.send_bytes(b"1")
        socket.send_bytes(b"2")
        assert "websocket send queue full" not in caplog.text


async def test_websocket_handshake__when_peer_gone_before_accept__should_end_quietly():
    async def connect() -> dict[str, str]:
        return {"type": "websocket.connect"}

    async def send_to_gone_peer(_message: object) -> None:
        raise OSError("client gone before the handshake")

    def gone_peer_websocket() -> WebSocket:
        return WebSocket({"type": "websocket", "path": "/", "headers": []}, receive=connect, send=send_to_gone_peer)

    await reject_websocket(gone_peer_websocket(), code=4000, reason="invalid_game_id")
    assert await accept_websocket(gone_peer_websocket()) is False
