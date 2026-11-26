import asyncio

from app.auth.models import AuthenticatedPlayer
from app.dal.models import AccountType
from app.matchmaking.websocket import matchmaking_websocket
from app.standby.websocket import standby_websocket
from tests.conftest import AsgiPeer, make_websocket

_STANDBY_BOT = AuthenticatedPlayer(
    user_id="ai-standby-id", username="ai-standby", account_type=AccountType.BOT, credential_hash="ai-standby-key"
)


async def test_matchmaking_websocket__when_bot_stands_by__should_reject_with_already_in_standby(app):
    standby_peer = AsgiPeer()
    standby_peer.send_gate = asyncio.Event()
    standby_handler = asyncio.create_task(standby_websocket(make_websocket(standby_peer, app=app, user=_STANDBY_BOT)))
    await standby_peer.send_waiting.wait()
    standby_peer.send_gate.set()

    queue_peer = AsgiPeer()
    queue_peer.disconnect()
    await matchmaking_websocket(make_websocket(queue_peer, app=app, user=_STANDBY_BOT))
    assert queue_peer.received_json() == [{"type": "error", "message": "already_in_standby"}]
    assert queue_peer.close_codes() == [4000]
    assert app.state.matchmaking_manager.queue_size == 0
    assert standby_peer.received_json() == [{"type": "standby_joined"}]

    standby_peer.disconnect()
    await standby_handler
    assert not app.state.bot_pool.has_idle
