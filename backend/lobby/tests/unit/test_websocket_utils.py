from lobby.tests.conftest import AsgiPeer, open_websocket
from lobby.websocket_utils import close_quietly, send_or_drop


async def test_send_or_drop__when_peer_is_gone__should_report_false_on_first_and_later_sends():
    peer = AsgiPeer()
    websocket = await open_websocket(peer)
    peer.broken = True

    assert await send_or_drop(websocket, "first") is False
    assert await send_or_drop(websocket, "second") is False


async def test_close_quietly__when_a_send_already_failed__should_not_raise():
    peer = AsgiPeer()
    websocket = await open_websocket(peer)
    peer.broken = True
    await send_or_drop(websocket, "lost")

    await close_quietly(websocket, code=4002, reason="room_expired")
