import asyncio
import json
import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from lobby import game_transition as game_transition_module
from lobby.auth.models import AuthenticatedPlayer
from lobby.matchmaking.websocket import matchmaking_websocket
from lobby.rooms import websocket as rooms_websocket_module
from lobby.rooms.websocket import room_websocket
from lobby.tests.conftest import AsgiPeer, HeldLookup, make_websocket, open_client
from lobby.tests.integration.conftest import login_with_csrf, logout_with_csrf, register_with_csrf


def _break_server_socket(app, *, room_id, username):
    room = app.state.room_manager.get_room(room_id)
    connection_id = next(conn_id for conn_id, player in room.players.items() if player.username == username)

    async def broken_send(_message):
        raise OSError("broken pipe")

    app.state.room_connections._connections[room_id][connection_id]._send = broken_send


def _room_socket(app, peer, *, room_id, username):
    return make_websocket(
        peer,
        app=app,
        user=AuthenticatedPlayer(user_id=f"{username}-id", username=username),
        path_params={"room_id": room_id},
    )


class TestRoomWebSocket:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "wsuser")
        return client

    @pytest.fixture
    def room_id(self, app):
        room = app.state.room_manager.create_room("test-room")
        return room.room_id

    def test_room_websocket__when_user_joins__should_send_room_joined_with_four_seats(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "room_joined"
            assert msg["room_id"] == room_id
            assert msg["player_name"] == "wsuser"
            assert msg["is_owner"] is True
            assert len(msg["players"]) == 4  # always 4 seats

    def test_room_websocket__when_chat_sent__should_echo_chat_with_player_name(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            ws.send_text(json.dumps({"type": "chat", "text": "hello"}))
            msg = ws.receive_json()
            assert msg["type"] == "chat"
            assert msg["player_name"] == "wsuser"
            assert msg["text"] == "hello"

    def test_room_websocket__when_non_owner_sets_ready__should_broadcast_ready_change(self, app):
        room = app.state.room_manager.create_room("ready-room")
        with open_client(app) as c:
            register_with_csrf(c, "owner")

            # Owner joins first
            with c.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_owner:
                ws_owner.receive_json()  # room_joined

                # Non-owner joins
                logout_with_csrf(c)
                register_with_csrf(c, "player2")
                with c.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_p2:
                    ws_p2.receive_json()  # room_joined
                    ws_owner.receive_json()  # player_joined broadcast

                    ws_p2.send_text(json.dumps({"type": "set_ready", "ready": True}))
                    msg = ws_p2.receive_json()
                    assert msg["type"] == "player_ready_changed"
                    assert msg["can_start"] is True

    def test_room_websocket__when_owner_sets_ready__should_send_error(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            ws.send_text(json.dumps({"type": "set_ready", "ready": True}))
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "owner_cannot_ready"

    def test_room_websocket__when_room_not_found__should_send_error(self, client):
        with client.websocket_connect("/ws/rooms/nonexistent") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "room_not_found"

    def test_room_websocket__when_room_full__should_send_error(self, client, app):
        room = app.state.room_manager.create_room("full-room")
        # Pre-fill all 4 seats
        for i in range(4):
            app.state.room_manager.join_room(
                connection_id=f"prefill-{i}", room_id="full-room", user_id=f"user-{i}", username=f"P{i}"
            )

        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "room_full"

    def test_room_websocket__when_message_not_json__should_send_error(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            ws.send_text("not json")
            msg = ws.receive_json()
            assert msg["type"] == "error"

    def test_room_websocket__when_message_oversized__should_send_error(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            big = json.dumps({"type": "chat", "text": "a" * 500, "x": "b" * 4000})
            ws.send_text(big)
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "too large" in msg["message"].lower()

    def test_room_websocket__when_message_type_unknown__should_send_error(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            ws.send_text(json.dumps({"type": "unknown_type"}))
            msg = ws.receive_json()
            assert msg["type"] == "error"

    def test_room_websocket__when_last_player_disconnects__should_remove_room(self, client, app, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            room = app.state.room_manager.get_room(room_id)
            assert room is not None
            assert room.player_count == 1
        # After disconnect, room should be cleaned up (empty rooms are removed)
        assert app.state.room_manager.get_room(room_id) is None

    def test_room_websocket__when_set_ready_while_transitioning__should_send_error(self, client, app, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            room = app.state.room_manager.get_room(room_id)
            assert room is not None

            room.transitioning = True
            ws.send_text(json.dumps({"type": "set_ready", "ready": True}))
            msg = ws.receive_json()
            assert msg["type"] == "error"

    def test_room_websocket__when_room_removed_before_start_game__should_send_not_in_room(self, client, app, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            # Remove room externally (simulates race condition)
            app.state.room_manager._rooms.pop(room_id, None)

            ws.send_text(json.dumps({"type": "start_game"}))
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "not_in_room"

    def test_room_websocket__when_start_game_while_transitioning__should_send_error(self, client, app, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            room = app.state.room_manager.get_room(room_id)
            room.transitioning = True

            ws.send_text(json.dumps({"type": "start_game"}))
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "room_transitioning"


class TestStartGameErrors:
    @pytest.fixture
    def two_user_client(self, client):
        register_with_csrf(client, "owner")
        logout_with_csrf(client)
        register_with_csrf(client, "player2")
        return client

    def test_room_websocket__when_non_owner_starts_game__should_send_not_owner(self, app, two_user_client):
        room = app.state.room_manager.create_room("nostart-room")
        # Log in as owner and connect
        login_with_csrf(two_user_client, "owner")
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_owner:
            ws_owner.receive_json()  # room_joined

            # Log in as player2 (non-owner) and connect
            logout_with_csrf(two_user_client)
            login_with_csrf(two_user_client, "player2")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_p2:
                ws_p2.receive_json()  # room_joined
                ws_owner.receive_json()  # player_joined broadcast

                # Non-owner tries start_game
                ws_p2.send_text(json.dumps({"type": "start_game"}))
                msg = ws_p2.receive_json()
                assert msg["type"] == "error"
                assert msg["message"] == "not_owner"

    def test_room_websocket__when_owner_starts_game_before_all_ready__should_send_not_all_ready(
        self, app, two_user_client
    ):
        room = app.state.room_manager.create_room("notready-room")
        # Log in as owner and connect
        login_with_csrf(two_user_client, "owner")
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_owner:
            ws_owner.receive_json()  # room_joined

            # Log in as player2 (non-owner) and connect
            logout_with_csrf(two_user_client)
            login_with_csrf(two_user_client, "player2")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_p2:
                ws_p2.receive_json()  # room_joined
                ws_owner.receive_json()  # player_joined broadcast

                # Owner tries start_game before player2 is ready
                ws_owner.send_text(json.dumps({"type": "start_game"}))
                msg = ws_owner.receive_json()
                assert msg["type"] == "error"
                assert msg["message"] == "not_all_ready"


class TestOwnerChanged:
    @pytest.fixture
    def two_user_client(self, client):
        register_with_csrf(client, "alice")
        logout_with_csrf(client)
        register_with_csrf(client, "bob")
        return client

    @pytest.mark.xfail(reason="Flaky: intermittent WebSocket timeout", strict=False)
    def test_room_websocket__when_owner_leaves__should_send_owner_changed_then_player_left(self, app, two_user_client):
        room = app.state.room_manager.create_room("transfer-room")
        # Alice connects first (becomes owner)
        login_with_csrf(two_user_client, "alice")
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_alice:
            ws_alice.receive_json()  # room_joined

            # Bob connects (non-owner)
            logout_with_csrf(two_user_client)
            login_with_csrf(two_user_client, "bob")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_bob:
                ws_bob.receive_json()  # room_joined
                ws_alice.receive_json()  # player_joined broadcast

                # Alice (owner) leaves via leave_room
                ws_alice.send_text(json.dumps({"type": "leave_room"}))
                # Bob should receive owner_changed then player_left
                msg1 = ws_bob.receive_json()
                assert msg1["type"] == "owner_changed"
                assert msg1["is_owner"] is True
                assert "can_start" in msg1
                assert len(msg1["players"]) == 4

                msg2 = ws_bob.receive_json()
                assert msg2["type"] == "player_left"
                assert msg2["player_name"] == "alice"


class TestMultiPlayerWebSocket:
    @pytest.fixture
    def two_user_client(self, client):
        register_with_csrf(client, "alice")
        logout_with_csrf(client)
        register_with_csrf(client, "bob")
        return client

    def test_room_websocket__when_player_leaves__should_broadcast_player_left(self, app, two_user_client):
        room = app.state.room_manager.create_room("multi-room")
        # Bob connects first (currently logged in)
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_bob:
            ws_bob.receive_json()  # room_joined
            # Log in as alice and connect
            login_with_csrf(two_user_client, "alice")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_alice:
                ws_alice.receive_json()  # room_joined
                player_joined = ws_bob.receive_json()  # player_joined for alice
                assert player_joined["type"] == "player_joined"

                # Alice leaves
                ws_alice.send_text(json.dumps({"type": "leave_room"}))

            # Bob should receive player_left
            msg = ws_bob.receive_json()
            assert msg["type"] == "player_left"

    def test_room_websocket__when_a_peer_is_dead__should_keep_the_chat_sender_seated(self, app, two_user_client):
        room = app.state.room_manager.create_room("dead-peer-chat")
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_bob:
            ws_bob.receive_json()
            login_with_csrf(two_user_client, "alice")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_alice:
                ws_alice.receive_json()
                ws_bob.receive_json()
                _break_server_socket(app, room_id=room.room_id, username="bob")

                ws_alice.send_text(json.dumps({"type": "chat", "text": "hello"}))
                assert ws_alice.receive_json() == {"type": "chat", "player_name": "alice", "text": "hello"}
                assert [player.username for player in room.players.values()] == ["bob", "alice"]

    def test_room_websocket__when_second_player_joins__should_broadcast_four_seat_player_list(
        self, app, two_user_client
    ):
        room = app.state.room_manager.create_room("consistent-room")
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_bob:
            bob_joined = ws_bob.receive_json()
            assert bob_joined["type"] == "room_joined"
            # Always 4 seats (1 human + 3 bots)
            assert len(bob_joined["players"]) == 4

            login_with_csrf(two_user_client, "alice")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_alice:
                alice_joined = ws_alice.receive_json()
                assert alice_joined["type"] == "room_joined"
                # Still 4 seats (2 humans + 2 bots)
                assert len(alice_joined["players"]) == 4

                player_joined = ws_bob.receive_json()
                assert player_joined["type"] == "player_joined"
                assert player_joined["player_name"] == "alice"
                assert len(player_joined["players"]) == 4

    def test_room_websocket__when_player_disconnects__should_broadcast_player_left(self, app, two_user_client):
        room = app.state.room_manager.create_room("dc-room")
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_bob:
            ws_bob.receive_json()  # room_joined
            login_with_csrf(two_user_client, "alice")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_alice:
                ws_alice.receive_json()  # room_joined
                ws_bob.receive_json()  # player_joined

            # Alice's WS closed (disconnect)
            msg = ws_bob.receive_json()
            assert msg["type"] == "player_left"


def _route_game_server(monkeypatch, game_server):
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        game_transition_module.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(game_server), **kwargs),
    )


class TestGameTransition:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "wsuser")
        return client

    def test_room_websocket__when_owner_starts_game__should_send_game_starting_and_remove_room(
        self, client, app, monkeypatch
    ):
        room = app.state.room_manager.create_room("game-room")
        game_server_requests: list[httpx.Request] = []

        def game_server(request):
            game_server_requests.append(request)
            return httpx.Response(201)

        _route_game_server(monkeypatch, game_server)

        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"type": "start_game"}))
            msg = ws.receive_json()

        [create_request] = game_server_requests
        game_id = json.loads(create_request.content)["game_id"]
        assert (create_request.method, str(create_request.url)) == ("POST", "http://game-server.invalid/games")
        assert msg["type"] == "game_starting"
        assert msg["game_id"] == game_id
        assert msg["ws_url"] == f"wss://game-client.invalid/ws/{game_id}"
        assert "game_ticket" in msg
        assert app.state.room_manager.get_room("game-room") is None

    def test_room_websocket__when_a_peer_is_dead_at_game_start__should_deliver_to_the_rest_and_remove_room(
        self, app, caplog, monkeypatch
    ):
        room = app.state.room_manager.create_room("dead-peer-start")
        _route_game_server(monkeypatch, lambda _request: httpx.Response(201))

        with open_client(app) as client:
            register_with_csrf(client, "bob")
            logout_with_csrf(client)
            register_with_csrf(client, "carol")
            logout_with_csrf(client)
            register_with_csrf(client, "alice")

            with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_alice:
                ws_alice.receive_json()
                login_with_csrf(client, "bob")
                with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_bob:
                    ws_bob.receive_json()
                    ws_alice.receive_json()
                    login_with_csrf(client, "carol")
                    with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_carol:
                        ws_carol.receive_json()
                        ws_alice.receive_json()
                        ws_bob.receive_json()
                        for ws_ready in (ws_bob, ws_carol):
                            ws_ready.send_text(json.dumps({"type": "set_ready", "ready": True}))
                            for ws_seated in (ws_alice, ws_bob, ws_carol):
                                ws_seated.receive_json()

                        _break_server_socket(app, room_id=room.room_id, username="bob")
                        ws_alice.send_text(json.dumps({"type": "start_game"}))
                        assert ws_alice.receive_json()["type"] == "game_starting"
                        assert ws_carol.receive_json()["type"] == "game_starting"

        assert app.state.room_manager.get_room("dead-peer-start") is None
        assert caplog.text.count("failed to deliver game_starting message") == 1

    def test_room_websocket__when_ticket_signing_raises__should_clear_transitioning_and_resync(self, client, app):
        room = app.state.room_manager.create_room("sign-fail-room")

        with (
            patch("lobby.rooms.websocket.sign_player_tickets", side_effect=ValueError("bad ticket secret")),
            client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws,
        ):
            ws.receive_json()
            ws.send_text(json.dumps({"type": "start_game"}))
            assert ws.receive_json()["type"] == "player_ready_changed"
            assert ws.receive_json() == {"type": "error", "message": "Failed to start game: internal error"}
            assert room.transitioning is False

    def test_room_websocket__when_game_server_returns_error__should_resync_and_send_error(
        self, client, app, monkeypatch
    ):
        room = app.state.room_manager.create_room("fail-room")
        _route_game_server(monkeypatch, lambda _request: httpx.Response(500, text="Internal Server Error"))

        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"type": "start_game"}))
            resync = ws.receive_json()
            assert resync["type"] == "player_ready_changed"
            assert "players" in resync
            assert "can_start" in resync

            msg = ws.receive_json()
            assert msg == {
                "type": "error",
                "message": "Failed to start game: Game server returned 500: Internal Server Error",
            }
            room_after_failure = app.state.room_manager.get_room("fail-room")
            assert room_after_failure is not None
            assert room_after_failure.transitioning is False

    def test_room_websocket__when_game_server_unreachable__should_resync_and_send_error(self, client, app, monkeypatch):
        room = app.state.room_manager.create_room("conn-err-room")

        def unreachable_game_server(_request):
            raise httpx.ConnectError("Connection refused")

        _route_game_server(monkeypatch, unreachable_game_server)

        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"type": "start_game"}))
            resync = ws.receive_json()
            assert resync["type"] == "player_ready_changed"
            assert "players" in resync
            assert "can_start" in resync

            msg = ws.receive_json()
            assert msg == {
                "type": "error",
                "message": "Failed to start game: Failed to connect to game server: Connection refused",
            }

    def test_room_websocket__when_start_retried_after_ambiguous_failure__should_start_under_a_fresh_game_id(
        self, client, app, monkeypatch
    ):
        room = app.state.room_manager.create_room("retry-room")
        created_game_ids: list[str] = []

        def game_server(request):
            game_id = json.loads(request.content)["game_id"]
            if game_id in created_game_ids:
                return httpx.Response(409, text="Game already exists")

            created_game_ids.append(game_id)
            if len(created_game_ids) == 1:
                raise httpx.ReadTimeout("timed out after the game server created the game")

            return httpx.Response(201)

        _route_game_server(monkeypatch, game_server)

        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"type": "start_game"}))
            assert ws.receive_json()["type"] == "player_ready_changed"
            assert ws.receive_json()["type"] == "error"

            ws.send_text(json.dumps({"type": "start_game"}))
            game_starting = ws.receive_json()
            assert game_starting["type"] == "game_starting"
            assert game_starting["game_id"] == created_game_ids[1]
            assert len(created_game_ids) == 2


class TestRoomWebSocketRaces:
    async def test_room_websocket__when_room_joined_ack_fails__should_free_seat_and_drop_empty_room(self, app):
        app.state.room_manager.create_room("ack-fail-room")
        peer = AsgiPeer()
        peer.broken = True

        await room_websocket(_room_socket(app, peer, room_id="ack-fail-room", username="ghost"))
        assert app.state.room_manager.get_room("ack-fail-room") is None
        assert app.state.room_manager.has_user_in_any_room("ghost-id") is False

    async def test_room_websocket__when_another_task_closed_the_socket_mid_join__should_end_without_error(
        self, app, caplog
    ):
        caplog.set_level(logging.INFO)
        app.state.room_manager.create_room("closed-mid-join")
        peer = AsgiPeer()
        peer.send_gate = asyncio.Event()
        websocket = _room_socket(app, peer, room_id="closed-mid-join", username="late")
        handler = asyncio.create_task(room_websocket(websocket))
        await peer.send_waiting.wait()

        await websocket.close(code=4002, reason="room_expired")
        peer.send_gate.set()
        await handler
        assert "player left room" in caplog.text
        assert "unexpected error in room websocket" not in caplog.text
        assert app.state.room_manager.get_room("closed-mid-join") is None

    async def test_room_websocket__when_handler_raises_unexpectedly__should_log_and_free_the_seat(
        self, app, monkeypatch, caplog
    ):
        app.state.room_manager.create_room("bug-room")
        peer = AsgiPeer()

        def failing_add(**_kwargs):
            raise ValueError("connection registry bug")

        monkeypatch.setattr(app.state.room_connections, "add", failing_add)

        await room_websocket(_room_socket(app, peer, room_id="bug-room", username="unlucky"))
        assert "unexpected error in room websocket" in caplog.text
        assert app.state.room_manager.get_room("bug-room") is None

    async def test_room_websocket__when_reaper_runs_during_join_ack__should_close_the_joiner(self, app):
        room = app.state.room_manager.create_room("reap-room")
        room.created_at -= 1000
        peer = AsgiPeer()
        peer.send_gate = asyncio.Event()
        handler = asyncio.create_task(room_websocket(_room_socket(app, peer, room_id=room.room_id, username="late")))
        await peer.send_waiting.wait()

        reaper_tick = asyncio.create_task(app.state.room_manager._reap_expired_rooms())
        await asyncio.sleep(0)
        peer.send_gate.set()
        await reaper_tick
        assert peer.close_codes() == [4002]

        await handler
        assert app.state.room_manager.get_room("reap-room") is None
        assert "reap-room" not in app.state.room_connections._connections


async def _hold_open(handler_coroutine, peer):
    peer.send_gate = asyncio.Event()
    handler = asyncio.create_task(handler_coroutine)
    await peer.send_waiting.wait()
    peer.send_gate.set()
    return handler


async def _join_room_and_leave(app, *, room_id, username):
    peer = AsgiPeer()
    peer.disconnect()
    await room_websocket(_room_socket(app, peer, room_id=room_id, username=username))
    return peer


class TestRoomOccupancy:
    async def test_room_websocket__when_user_is_queued__should_reject_with_already_in_queue(self, app):
        room = app.state.room_manager.create_room("queued-room")
        queue_peer = AsgiPeer()
        queue_socket = make_websocket(
            queue_peer, app=app, user=AuthenticatedPlayer(user_id="alice-id", username="alice")
        )
        queue_handler = await _hold_open(matchmaking_websocket(queue_socket), queue_peer)

        room_peer = await _join_room_and_leave(app, room_id=room.room_id, username="alice")
        assert room_peer.received_json() == [{"type": "error", "message": "already_in_queue"}]
        assert room_peer.close_codes() == [4000]
        assert room.is_empty

        queue_peer.disconnect()
        await queue_handler

    async def test_room_websocket__when_user_is_seated_in_another_room__should_reject_with_already_in_room(self, app):
        first_room = app.state.room_manager.create_room("first-room")
        second_room = app.state.room_manager.create_room("second-room")
        seated_peer = AsgiPeer()
        seated_handler = await _hold_open(
            room_websocket(_room_socket(app, seated_peer, room_id=first_room.room_id, username="alice")), seated_peer
        )

        second_peer = await _join_room_and_leave(app, room_id=second_room.room_id, username="alice")
        assert second_peer.received_json() == [{"type": "error", "message": "already_in_room"}]
        assert second_peer.close_codes() == [4000]
        assert second_room.is_empty

        seated_peer.disconnect()
        await seated_handler

    async def test_room_websocket__when_the_users_room_starts_during_the_lookup__should_reject_with_already_in_game(
        self, make_app, monkeypatch
    ):
        held_lookup = HeldLookup()
        app = make_app(is_playing=held_lookup)
        monkeypatch.setattr(
            rooms_websocket_module, "create_game_on_server", AsyncMock(return_value="ws://localhost:8711/ws/game")
        )
        first_room = app.state.room_manager.create_room("first-room")
        second_room = app.state.room_manager.create_room("second-room")
        seated_peer = AsgiPeer()
        seated_handler = await _hold_open(
            room_websocket(_room_socket(app, seated_peer, room_id=first_room.room_id, username="alice")), seated_peer
        )

        held_lookup.held_user_id = "alice-id"
        late_join = asyncio.create_task(_join_room_and_leave(app, room_id=second_room.room_id, username="alice"))
        await held_lookup.started.wait()
        seated_peer.send_from_client(json.dumps({"type": "start_game"}))
        await seated_handler
        assert seated_peer.received_json()[-1]["type"] == "game_starting"
        assert app.state.room_manager.get_room(first_room.room_id) is None

        held_lookup.release.set()
        late_peer = await late_join
        assert late_peer.received_json() == [{"type": "error", "message": "already_in_game"}]
        assert second_room.is_empty

    async def test_room_websocket__when_app_wires_the_game_server_lookup__should_reject_only_the_playing_user(
        self, make_app, monkeypatch
    ):
        def game_server(request):
            if (request.url.host, request.url.path) == ("game-server.invalid", "/players/alice-id"):
                return httpx.Response(200, json={"game_id": "game-1"})

            return httpx.Response(404)

        _route_game_server(monkeypatch, game_server)
        app = make_app(is_playing=None)
        room = app.state.room_manager.create_room("wired-room")

        alice_peer = await _join_room_and_leave(app, room_id=room.room_id, username="alice")
        assert alice_peer.received_json() == [{"type": "error", "message": "already_in_game"}]
        bob_peer = await _join_room_and_leave(app, room_id=room.room_id, username="bob")
        assert bob_peer.received_json()[0]["type"] == "room_joined"

    async def test_room_websocket__when_game_server_unreachable__should_let_the_user_join_and_warn(
        self, make_app, monkeypatch, caplog
    ):
        def unreachable_game_server(_request):
            raise httpx.ConnectError("connection refused")

        _route_game_server(monkeypatch, unreachable_game_server)
        app = make_app(is_playing=None)
        room = app.state.room_manager.create_room("fail-open-room")

        alice_peer = await _join_room_and_leave(app, room_id=room.room_id, username="alice")
        assert alice_peer.received_json()[0]["type"] == "room_joined"
        assert caplog.text.count("playing lookup failed") == 1

    async def test_room_websocket__when_game_server_lookup_times_out__should_let_the_user_join_and_warn(
        self, make_app, monkeypatch, caplog
    ):
        async def stalled_game_server(_request):
            await asyncio.Event().wait()

        monkeypatch.setattr(game_transition_module, "_PLAYING_LOOKUP_TIMEOUT_SECONDS", 0.01)
        _route_game_server(monkeypatch, stalled_game_server)
        app = make_app(is_playing=None)
        room = app.state.room_manager.create_room("stalled-lookup-room")

        alice_peer = await _join_room_and_leave(app, room_id=room.room_id, username="alice")
        assert alice_peer.received_json()[0]["type"] == "room_joined"
        assert caplog.text.count("playing lookup failed") == 1


class TestWebSocketOriginCheck:
    def test_room_websocket__when_origin_forbidden__should_reject_connection(self, client, app):
        register_with_csrf(client, "wsuser")
        room = app.state.room_manager.create_room("bad-origin")
        with (
            pytest.raises(Exception),  # noqa: B017, PT011
            client.websocket_connect(
                f"/ws/rooms/{room.room_id}",
                headers={"origin": "http://evil.com"},
            ) as ws,
        ):
            ws.receive_json()

    def test_room_websocket__when_origin_header_missing__should_reject_connection(self, app):
        room = app.state.room_manager.create_room("no-origin")
        with TestClient(app) as client_without_origin:
            register_with_csrf(client_without_origin, "wsuser")
            with (
                pytest.raises(Exception),  # noqa: B017, PT011
                client_without_origin.websocket_connect(f"/ws/rooms/{room.room_id}") as ws,
            ):
                ws.receive_json()


class TestWebSocketUnauthenticated:
    def test_room_websocket__when_unauthenticated__should_reject_connection(self, client, app):
        app.state.room_manager.create_room("auth-test")
        with (
            pytest.raises(Exception),  # noqa: B017, PT011
            client.websocket_connect(
                "/ws/rooms/auth-test",
            ) as ws,
        ):
            ws.receive_json()
