import asyncio
import json
from unittest.mock import patch

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from lobby import game_transition as game_transition_module
from lobby.auth.models import AuthenticatedPlayer
from lobby.matchmaking.websocket import matchmaking_websocket
from lobby.rooms import websocket as rooms_websocket_module
from lobby.rooms.websocket import room_websocket
from lobby.tests.conftest import AsgiPeer, HeldLookup, make_player, make_websocket, open_client
from lobby.tests.integration.conftest import login_with_csrf, logout_with_csrf, register_with_csrf


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
                room_id="full-room",
                player=make_player(connection_id=f"prefill-{i}", user_id=f"user-{i}", username=f"P{i}"),
            )

        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "room_full"

    @pytest.mark.parametrize(
        "send_invalid_frame",
        [lambda ws: ws.send_text("not json"), lambda ws: ws.send_bytes(b"\x81")],
        ids=["text_not_json", "binary"],
    )
    def test_room_websocket__when_frame_is_not_json_text__should_send_error_and_keep_the_seat(
        self, client, app, room_id, send_invalid_frame
    ):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            send_invalid_frame(ws)
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert app.state.room_manager.get_room(room_id).player_count == 1

    def test_room_websocket__when_messages_exceed_the_burst__should_drop_them_with_rate_limited(
        self, client, room_id, monkeypatch
    ):
        monkeypatch.setattr(rooms_websocket_module, "_RATE_LIMIT_RATE", 0.0)
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()
            for i in range(11):
                ws.send_text(json.dumps({"type": "chat", "text": str(i)}))
            replies = [ws.receive_json() for _ in range(11)]

        assert [reply["text"] for reply in replies[:10]] == [str(i) for i in range(10)]
        assert replies[10] == {"type": "error", "message": "rate_limited"}

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


class TestGameTransition:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "wsuser")
        return client

    def test_room_websocket__when_owner_starts_game__should_send_game_starting_and_remove_room(
        self, client, app, game_server
    ):
        room = app.state.room_manager.create_room("game-room")
        game_server_requests: list[httpx.Request] = []

        def create_game(request: httpx.Request) -> httpx.Response:
            game_server_requests.append(request)
            return httpx.Response(201)

        game_server.respond = create_game

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

    async def test_room_websocket__when_a_peer_is_held_at_game_start__should_deliver_to_the_rest_and_remove_room(
        self, app, game_server
    ):
        game_server.respond = lambda _request: httpx.Response(201)
        room = app.state.room_manager.create_room("held-peer-start")
        host_peer, host_handler = await _seat(app, room_id=room.room_id, username="alice")
        held_peer, held_handler = await _seat(app, room_id=room.room_id, username="bob")
        late_peer, late_handler = await _seat(app, room_id=room.room_id, username="carol")
        for member in room.players.values():
            member.ready = True
        held_peer.send_gate = asyncio.Event()

        host_peer.send_from_client(json.dumps({"type": "start_game"}))
        await host_handler
        await late_handler
        assert late_peer.received_json()[-1]["type"] == "game_starting"
        assert late_peer.close_codes() == [1000]
        assert app.state.room_manager.get_room("held-peer-start") is None
        assert "game_starting" not in [message["type"] for message in held_peer.received_json()]

        held_peer.send_gate.set()
        await held_handler
        assert held_peer.received_json()[-1]["type"] == "game_starting"
        assert held_peer.close_codes() == [1000]

    def test_room_websocket__when_ticket_signing_raises__should_clear_transitioning_and_resync(self, client, app):
        room = app.state.room_manager.create_room("sign-fail-room")

        with (
            patch("lobby.game_transition.create_signed_ticket", side_effect=ValueError("bad ticket secret")),
            client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws,
        ):
            ws.receive_json()
            ws.send_text(json.dumps({"type": "start_game"}))
            assert ws.receive_json()["type"] == "player_ready_changed"
            assert ws.receive_json() == {"type": "error", "message": "internal_error"}
            assert room.transitioning is False

    @pytest.mark.parametrize(
        ("status", "reason"),
        [(500, "game_server_error"), (503, "game_server_full"), (409, "player_in_game")],
    )
    def test_room_websocket__when_game_server_refuses_the_game__should_resync_and_send_a_fixed_reason(
        self, client, app, game_server, status, reason
    ):
        room = app.state.room_manager.create_room("fail-room")
        game_server.respond = lambda _request: httpx.Response(status, json={"error": "game server text"})

        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"type": "start_game"}))
            resync = ws.receive_json()
            assert resync["type"] == "player_ready_changed"
            assert "players" in resync
            assert "can_start" in resync

            assert ws.receive_json() == {"type": "error", "message": reason}
            room_after_failure = app.state.room_manager.get_room("fail-room")
            assert room_after_failure is not None
            assert room_after_failure.transitioning is False

    def test_room_websocket__when_game_server_unreachable__should_resync_and_send_a_fixed_reason(self, client, app):
        room = app.state.room_manager.create_room("conn-err-room")

        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
            ws.receive_json()
            ws.send_text(json.dumps({"type": "start_game"}))
            assert ws.receive_json()["type"] == "player_ready_changed"
            assert ws.receive_json() == {"type": "error", "message": "game_server_unavailable"}

    def test_room_websocket__when_start_retried_after_ambiguous_failure__should_start_under_a_fresh_game_id(
        self, client, app, game_server
    ):
        room = app.state.room_manager.create_room("retry-room")
        created_game_ids: list[str] = []

        def create_game(request: httpx.Request) -> httpx.Response:
            game_id = json.loads(request.content)["game_id"]
            if game_id in created_game_ids:
                return httpx.Response(409, text="Game already exists")

            created_game_ids.append(game_id)
            if len(created_game_ids) == 1:
                raise httpx.ReadTimeout("timed out after the game server created the game")

            return httpx.Response(201)

        game_server.respond = create_game

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

    async def test_room_websocket__when_handler_raises_unexpectedly__should_log_and_free_the_seat(
        self, app, monkeypatch, caplog
    ):
        app.state.room_manager.create_room("bug-room")
        peer = AsgiPeer()
        peer.send_from_client(json.dumps({"type": "set_ready", "ready": True}))

        def failing_set_ready(*_args, **_kwargs):
            raise ValueError("room manager bug")

        monkeypatch.setattr(app.state.room_manager, "set_ready", failing_set_ready)

        await room_websocket(_room_socket(app, peer, room_id="bug-room", username="unlucky"))
        assert "unexpected error in room websocket" in caplog.text
        assert app.state.room_manager.get_room("bug-room") is None

    async def test_room_websocket__when_a_player_readies_during_a_join_ack__should_send_the_joiner_the_change(
        self, app
    ):
        room = app.state.room_manager.create_room("ready-during-ack")
        host_peer, host_handler = await _seat(app, room_id=room.room_id, username="alice")
        guest_peer, guest_handler = await _seat(app, room_id=room.room_id, username="bob")
        joiner_peer = AsgiPeer()
        joiner_peer.send_gate = asyncio.Event()
        joiner_handler = asyncio.create_task(
            room_websocket(_room_socket(app, joiner_peer, room_id=room.room_id, username="carol"))
        )
        await joiner_peer.send_waiting.wait()

        guest_peer.send_from_client(json.dumps({"type": "set_ready", "ready": True}))
        guest_peer.send_from_client(json.dumps({"type": "leave_room"}))
        await guest_handler
        joiner_peer.send_gate.set()
        joiner_peer.send_from_client(json.dumps({"type": "leave_room"}))
        await joiner_handler
        joiner_messages = joiner_peer.received_json()
        assert [message["type"] for message in joiner_messages] == [
            "room_joined",
            "player_ready_changed",
            "player_left",
        ]
        assert joiner_messages[1]["players"][1] == {"name": "bob", "ready": True, "is_bot": False, "is_owner": False}

        host_peer.disconnect()
        await host_handler

    async def test_room_chat__when_a_peer_is_held__should_not_block_the_sender(self, app):
        room = app.state.room_manager.create_room("held-peer-chat")
        held_peer, held_handler = await _seat(app, room_id=room.room_id, username="bob")
        sender_peer, sender_handler = await _seat(app, room_id=room.room_id, username="alice")
        held_peer.send_gate = asyncio.Event()

        sender_peer.send_from_client(json.dumps({"type": "chat", "text": "hello"}))
        sender_peer.send_from_client(json.dumps({"type": "set_ready", "ready": True}))
        sender_peer.send_from_client(json.dumps({"type": "leave_room"}))
        await sender_handler
        assert [message["type"] for message in sender_peer.received_json()] == [
            "room_joined",
            "chat",
            "player_ready_changed",
        ]
        assert sender_peer.close_codes() == [1000]

        held_peer.send_gate.set()
        held_peer.disconnect()
        await held_handler

    async def test_room_reaper__when_a_member_of_an_expired_room_is_held__should_still_close_the_later_rooms(
        self, app, caplog
    ):
        held_room = app.state.room_manager.create_room("held-room")
        later_room = app.state.room_manager.create_room("later-room")
        held_room.created_at -= 1000
        later_room.created_at -= 1000
        held_peer = AsgiPeer()
        held_peer.send_gate = asyncio.Event()
        held_handler = asyncio.create_task(
            room_websocket(_room_socket(app, held_peer, room_id=held_room.room_id, username="alice"))
        )
        await held_peer.send_waiting.wait()
        later_peer, later_handler = await _seat(app, room_id=later_room.room_id, username="bob")

        app.state.room_manager._reap_expired_rooms()
        await later_handler
        assert later_peer.close_codes() == [4002]
        assert app.state.room_manager.get_room("held-room") is None
        assert app.state.room_manager.get_room("later-room") is None

        held_peer.send_gate.set()
        await held_handler
        assert [message["type"] for message in held_peer.received_json()] == ["room_joined"]
        assert held_peer.close_codes() == [4002]
        assert "unexpected error in room websocket" not in caplog.text


async def _hold_open(handler_coroutine, peer):
    peer.send_gate = asyncio.Event()
    handler = asyncio.create_task(handler_coroutine)
    await peer.send_waiting.wait()
    peer.send_gate.set()
    return handler


async def _seat(app, *, room_id, username):
    peer = AsgiPeer()
    handler = await _hold_open(room_websocket(_room_socket(app, peer, room_id=room_id, username=username)), peer)
    return peer, handler


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
        self, make_app, game_server
    ):
        held_lookup = HeldLookup()
        app = make_app(is_playing=held_lookup)
        game_server.respond = lambda _request: httpx.Response(201)
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
        self, make_app, game_server
    ):
        def find_player_game(request: httpx.Request) -> httpx.Response:
            if (request.url.host, request.url.path) == ("game-server.invalid", "/players/alice-id"):
                return httpx.Response(200, json={"game_id": "game-1"})

            return httpx.Response(404)

        game_server.respond = find_player_game
        app = make_app(is_playing=None)
        room = app.state.room_manager.create_room("wired-room")

        alice_peer = await _join_room_and_leave(app, room_id=room.room_id, username="alice")
        assert alice_peer.received_json() == [{"type": "error", "message": "already_in_game"}]
        bob_peer = await _join_room_and_leave(app, room_id=room.room_id, username="bob")
        assert bob_peer.received_json()[0]["type"] == "room_joined"

    async def test_room_websocket__when_game_server_unreachable__should_let_the_user_join_and_warn(
        self, make_app, caplog
    ):
        app = make_app(is_playing=None)
        room = app.state.room_manager.create_room("fail-open-room")

        alice_peer = await _join_room_and_leave(app, room_id=room.room_id, username="alice")
        assert alice_peer.received_json()[0]["type"] == "room_joined"
        assert caplog.text.count("playing lookup failed") == 1

    async def test_room_websocket__when_game_server_lookup_times_out__should_let_the_user_join_and_warn(
        self, make_app, game_server, monkeypatch, caplog
    ):
        async def stalled_game_server(_request):
            await asyncio.Event().wait()

        monkeypatch.setattr(game_transition_module, "_PLAYING_LOOKUP_TIMEOUT_SECONDS", 0.01)
        game_server.respond = stalled_game_server
        app = make_app(is_playing=None)
        room = app.state.room_manager.create_room("stalled-lookup-room")

        alice_peer = await _join_room_and_leave(app, room_id=room.room_id, username="alice")
        assert alice_peer.received_json()[0]["type"] == "room_joined"
        assert caplog.text.count("playing lookup failed") == 1


class TestWebSocketOriginCheck:
    def test_room_websocket__when_origin_forbidden__should_close_with_4003(self, client, app):
        register_with_csrf(client, "wsuser")
        room = app.state.room_manager.create_room("bad-origin")
        with (
            pytest.raises(WebSocketDisconnect) as rejection,
            client.websocket_connect(f"/ws/rooms/{room.room_id}", headers={"origin": "http://evil.com"}),
        ):
            pass
        assert rejection.value.code == 4003

    def test_room_websocket__when_origin_header_missing__should_close_with_4003(self, app):
        room = app.state.room_manager.create_room("no-origin")
        with TestClient(app) as client_without_origin:
            register_with_csrf(client_without_origin, "wsuser")
            with (
                pytest.raises(WebSocketDisconnect) as rejection,
                client_without_origin.websocket_connect(f"/ws/rooms/{room.room_id}"),
            ):
                pass
        assert rejection.value.code == 4003


class TestWebSocketUnauthenticated:
    def test_room_websocket__when_unauthenticated__should_close_with_4001(self, client, app):
        app.state.room_manager.create_room("auth-test")
        with pytest.raises(WebSocketDisconnect) as rejection, client.websocket_connect("/ws/rooms/auth-test"):
            pass
        assert rejection.value.code == 4001
