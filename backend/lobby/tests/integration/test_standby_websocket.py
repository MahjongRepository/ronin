import asyncio
import json

import httpx

from app.auth.models import AuthenticatedPlayer
from app.dal.models import AccountType
from app.matchmaking.websocket import matchmaking_websocket
from app.rooms.websocket import room_websocket
from app.standby.websocket import standby_websocket
from tests.conftest import AsgiPeer, make_websocket

_STANDBY_BOT = AuthenticatedPlayer(
    user_id="ai-standby-id", username="ai-standby", account_type=AccountType.BOT, credential_hash="ai-standby-key"
)
_STRONG_BOTS = [
    AuthenticatedPlayer(
        user_id=f"ai-strong-{n}-id", username=f"ai-strong-{n}", account_type=AccountType.BOT, credential_hash=f"key-{n}"
    )
    for n in (1, 2)
]
_OWNER = AuthenticatedPlayer(user_id="alice-id", username="alice", credential_hash="alice-session")


async def _hold_open(handler_coroutine, peer):
    peer.send_gate = asyncio.Event()
    handler = asyncio.create_task(handler_coroutine)
    await peer.send_waiting.wait()
    peer.send_gate.set()
    return handler


async def _stand_by(app, user):
    peer = AsgiPeer()
    handler = await _hold_open(standby_websocket(make_websocket(peer, app=app, user=user)), peer)
    return peer, handler


async def _seat(app, *, room_id, user):
    peer = AsgiPeer()
    socket = make_websocket(peer, app=app, user=user, path_params={"room_id": room_id})
    handler = await _hold_open(room_websocket(socket), peer)
    return peer, handler


async def test_matchmaking_websocket__when_bot_stands_by__should_reject_with_already_in_standby(app):
    standby_peer, standby_handler = await _stand_by(app, _STANDBY_BOT)

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


async def test_room_websocket__when_owner_starts_with_strong_bots__should_start_the_game_with_the_idle_standby_bots(
    app, game_server
):
    bot_pool = app.state.bot_pool
    create_bodies: list[dict] = []
    claimed_during_create: list[bool] = []

    def create_game(request: httpx.Request) -> httpx.Response:
        create_bodies.append(json.loads(request.content))
        claimed_during_create.extend(bot_pool.is_claimed(bot.user_id) for bot in _STRONG_BOTS)
        return httpx.Response(201)

    game_server.respond = create_game
    bots = [await _stand_by(app, bot) for bot in _STRONG_BOTS]
    room = app.state.room_manager.create_room("strong-room")
    owner_peer, owner_handler = await _seat(app, room_id=room.room_id, user=_OWNER)

    owner_peer.send_from_client(json.dumps({"type": "start_game", "use_strong_bots": True}))
    await owner_handler
    for _peer, handler in bots:
        await handler

    [body] = create_bodies
    assert owner_peer.received_json()[0]["strong_bots_available"] is True
    assert claimed_during_create == [True, True]
    assert sorted(player["user_id"] for player in body["players"]) == sorted(
        [_OWNER.user_id, *(bot.user_id for bot in _STRONG_BOTS)]
    )
    assert body["num_ai_players"] == 1
    for peer, _handler in bots:
        bot_messages = peer.received_json()
        assert [message["type"] for message in bot_messages] == ["standby_joined", "game_starting"]
        assert bot_messages[-1]["game_id"] == body["game_id"]
        assert peer.close_codes() == [1000]
    assert not bot_pool.has_idle
    assert not any(bot_pool.is_claimed(bot.user_id) for bot in _STRONG_BOTS)


async def test_room_websocket__when_strong_bots_start_fails__should_close_the_claimed_bots(app):
    bot_pool = app.state.bot_pool
    bots = [await _stand_by(app, bot) for bot in _STRONG_BOTS]
    room = app.state.room_manager.create_room("failing-strong-room")
    owner_peer, owner_handler = await _seat(app, room_id=room.room_id, user=_OWNER)

    owner_peer.send_from_client(json.dumps({"type": "start_game", "use_strong_bots": True}))
    for _peer, handler in bots:
        await handler
    owner_peer.disconnect()
    await owner_handler

    for peer, _handler in bots:
        assert peer.received_json() == [{"type": "standby_joined"}]
        assert peer.close_codes() == [1000]
    assert not bot_pool.has_idle
    assert not any(bot_pool.is_claimed(bot.user_id) for bot in _STRONG_BOTS)
    owner_messages = owner_peer.received_json()
    assert [message["type"] for message in owner_messages] == ["room_joined", "player_ready_changed", "error"]
    assert owner_messages[1]["strong_bots_available"] is False
    assert owner_messages[-1] == {"type": "error", "message": "game_server_unavailable"}
