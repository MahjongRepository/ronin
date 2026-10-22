import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from lobby.auth.models import AuthenticatedPlayer
from lobby.game_transition import GameTransitionError
from lobby.matchmaking import websocket as matchmaking_websocket_module
from lobby.matchmaking.websocket import matchmaking_websocket
from lobby.server.app import create_app
from lobby.settings import LobbyServerSettings
from lobby.tests.conftest import AsgiPeer, HeldLookup, make_websocket, nobody_playing
from lobby.tests.integration.conftest import register_with_csrf
from shared.auth.game_ticket import verify_game_ticket
from shared.auth.settings import AuthSettings


def _make_app(tmp_path, *, is_playing=nobody_playing, **settings_kwargs):
    config_file = tmp_path / "servers.yaml"
    servers_yaml = """
servers:
  - name: "test-server"
    url: "http://localhost:8711"
    client_url: "http://localhost:8711"
"""
    config_file.write_text(servers_yaml)

    static_dir = tmp_path / "public"
    (static_dir / "styles").mkdir(parents=True)
    (static_dir / "styles" / "lobby.css").write_text("/* test */")

    settings_kwargs.setdefault("ws_allowed_origin", None)
    return create_app(
        settings=LobbyServerSettings(
            config_path=config_file,
            static_dir=str(static_dir),
            **settings_kwargs,
        ),
        auth_settings=AuthSettings(
            game_ticket_secret="test-secret",
            database_path=str(tmp_path / "test.db"),
            cookie_secure=False,
        ),
        is_playing=is_playing,
    )


def _matchmaking_socket(app, peer, *, username):
    return make_websocket(peer, app=app, user=AuthenticatedPlayer(user_id=f"{username}-id", username=username))


async def _queue_player(app, username):
    peer = AsgiPeer()
    peer.send_gate = asyncio.Event()
    handler = asyncio.create_task(matchmaking_websocket(_matchmaking_socket(app, peer, username=username)))
    await peer.send_waiting.wait()
    peer.send_gate.set()
    return peer, handler


class TestMatchmakingWebSocket:
    @pytest.fixture
    def app(self, tmp_path):
        return _make_app(tmp_path)

    @pytest.fixture
    def client(self, app):
        with TestClient(app) as c:
            register_with_csrf(c, "player1")
            yield c

    def test_matchmaking_websocket__when_authenticated_client_connects__should_send_queue_joined(self, client):
        with client.websocket_connect("/ws/matchmaking") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "queue_joined"
            assert msg["queue_size"] == 1
            assert msg["position"] == 1

    def test_matchmaking_websocket__when_ping_sent__should_reply_pong(self, client):
        with client.websocket_connect("/ws/matchmaking") as ws:
            ws.receive_json()  # queue_joined
            ws.send_text(json.dumps({"type": "ping"}))
            msg = ws.receive_json()
            assert msg["type"] == "pong"

    def test_matchmaking_websocket__when_message_not_json__should_send_error(self, client):
        with client.websocket_connect("/ws/matchmaking") as ws:
            ws.receive_json()  # queue_joined
            ws.send_text("not json")
            msg = ws.receive_json()
            assert msg["type"] == "error"

    def test_matchmaking_websocket__when_message_type_unknown__should_send_error(self, client):
        with client.websocket_connect("/ws/matchmaking") as ws:
            ws.receive_json()  # queue_joined
            ws.send_text(json.dumps({"type": "unknown"}))
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "Invalid message format"

    def test_matchmaking_websocket__when_message_oversized__should_send_error(self, client):
        with client.websocket_connect("/ws/matchmaking") as ws:
            ws.receive_json()  # queue_joined
            big = json.dumps({"type": "ping", "padding": "x" * 5000})
            ws.send_text(big)
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "too large" in msg["message"].lower()

    def test_matchmaking_websocket__when_client_disconnects__should_remove_from_queue(self, app, client):
        with client.websocket_connect("/ws/matchmaking"):
            assert app.state.matchmaking_manager.queue_size == 1
        assert app.state.matchmaking_manager.queue_size == 0

    async def test_matchmaking_websocket__when_already_in_queue__should_reject_the_second_socket(self, app):
        first_peer, first_handler = await _queue_player(app, "alice")

        second_peer = AsgiPeer()
        await matchmaking_websocket(_matchmaking_socket(app, second_peer, username="alice"))
        assert second_peer.received_json() == [{"type": "error", "message": "already_in_queue"}]
        assert second_peer.close_codes() == [4000]
        assert app.state.matchmaking_manager.queue_size == 1

        first_peer.disconnect()
        await first_handler

    async def test_matchmaking_websocket__when_user_is_playing__should_reject_with_already_in_game(self, tmp_path):
        async def alice_playing(user_id):
            return user_id == "alice-id"

        app = _make_app(tmp_path, is_playing=alice_playing)

        peer = AsgiPeer()
        await matchmaking_websocket(_matchmaking_socket(app, peer, username="alice"))
        assert peer.received_json() == [{"type": "error", "message": "already_in_game"}]
        assert peer.close_codes() == [4000]
        assert app.state.matchmaking_manager.queue_size == 0

    def test_matchmaking_websocket__when_already_in_room__should_send_error(self, app, client):
        room = app.state.room_manager.create_room("test-room")
        # Join the room first
        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_room:
            ws_room.receive_json()  # room_joined
            # Now try matchmaking
            with client.websocket_connect("/ws/matchmaking") as ws_mm:
                msg = ws_mm.receive_json()
                assert msg["type"] == "error"
                assert msg["message"] == "already_in_room"


class TestMatchmakingUnauthenticated:
    @pytest.fixture
    def unauthenticated_client(self, tmp_path):
        app = _make_app(tmp_path)
        with TestClient(app) as c:
            yield c

    def test_matchmaking_websocket__when_unauthenticated__should_reject_connection(self, unauthenticated_client):
        with (
            pytest.raises(Exception),  # noqa: B017, PT011
            unauthenticated_client.websocket_connect("/ws/matchmaking") as ws,
        ):
            ws.receive_json()


class TestMatchmakingOriginCheck:
    @pytest.fixture
    def app_with_origin(self, tmp_path):
        return _make_app(tmp_path, ws_allowed_origin="http://localhost:3000")

    @pytest.fixture
    def client_with_origin(self, app_with_origin):
        with TestClient(app_with_origin) as c:
            register_with_csrf(c, "player1")
            yield c

    def test_matchmaking_websocket__when_origin_allowed__should_connect(self, client_with_origin):
        with client_with_origin.websocket_connect(
            "/ws/matchmaking",
            headers={"origin": "http://localhost:3000"},
        ) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "queue_joined"

    def test_matchmaking_websocket__when_origin_forbidden__should_reject_connection(self, client_with_origin):
        with (
            pytest.raises(Exception),  # noqa: B017, PT011
            client_with_origin.websocket_connect(
                "/ws/matchmaking",
                headers={"origin": "http://evil.com"},
            ) as ws,
        ):
            ws.receive_json()


class TestMatchmakingGameTransition:
    @pytest.fixture
    def app(self, tmp_path):
        return _make_app(tmp_path)

    async def test_matchmaking_websocket__when_game_creation_fails__should_close_all_four_and_let_them_queue_again(
        self, app, monkeypatch
    ):
        monkeypatch.setattr(
            matchmaking_websocket_module,
            "create_game_on_server",
            AsyncMock(side_effect=GameTransitionError("read timed out after the game server got the request")),
        )
        queued = [await _queue_player(app, f"queued-{i}") for i in range(3)]
        fourth_peer = AsgiPeer()

        await matchmaking_websocket(_matchmaking_socket(app, fourth_peer, username="fourth"))
        for peer in [*(peer for peer, _handler in queued), fourth_peer]:
            assert peer.received_json()[-1] == {"type": "error", "message": "match_failed"}
            assert peer.close_codes() == [4000]

        for _peer, handler in queued:
            await handler

        rejoining_peer = AsgiPeer()
        rejoining_peer.disconnect()
        await matchmaking_websocket(_matchmaking_socket(app, rejoining_peer, username="queued-0"))
        assert rejoining_peer.received_json()[0]["type"] == "queue_joined"

    async def test_matchmaking_websocket__when_a_matched_peer_is_dead__should_start_the_game_for_the_rest(
        self, app, monkeypatch, caplog
    ):
        create_game = AsyncMock(return_value="ws://localhost:8711/ws/game")
        monkeypatch.setattr(matchmaking_websocket_module, "create_game_on_server", create_game)
        queued = [await _queue_player(app, f"queued-{i}") for i in range(3)]
        dead_peer, _dead_handler = queued[1]
        dead_peer.broken = True
        fourth_peer = AsgiPeer()

        await matchmaking_websocket(_matchmaking_socket(app, fourth_peer, username="fourth"))
        healthy_peers = {"queued-0": queued[0][0], "queued-2": queued[2][0], "fourth": fourth_peer}
        for username, peer in healthy_peers.items():
            game_starting = peer.received_json()[-1]
            ticket = verify_game_ticket(game_starting["game_ticket"], "test-secret")
            assert game_starting["type"] == "game_starting"
            assert game_starting["game_id"] == create_game.call_args.kwargs["game_id"]
            assert ticket is not None
            assert ticket.username == username
            assert peer.close_codes() == [1000]
        assert caplog.text.count("failed to deliver game_starting") == 1

        dead_peer.disconnect(code=1006)
        for _peer, handler in queued:
            await handler
        assert app.state.matchmaking_manager.queue_size == 0

    @pytest.mark.parametrize(
        ("create_game", "first_player_last_message"),
        [
            (AsyncMock(return_value="ws://localhost:8711/ws/game"), "game_starting"),
            (
                AsyncMock(side_effect=GameTransitionError("read timed out after the game server got the request")),
                "error",
            ),
        ],
        ids=["created", "creation_failed_after_the_game_server_got_it"],
    )
    async def test_matchmaking_websocket__when_a_match_starts_during_the_lookup__should_reject_with_already_in_game(
        self, tmp_path, monkeypatch, create_game, first_player_last_message
    ):
        held_lookup = HeldLookup()
        app = _make_app(tmp_path, is_playing=held_lookup)
        monkeypatch.setattr(matchmaking_websocket_module, "create_game_on_server", create_game)
        queued = [await _queue_player(app, username) for username in ("alice", "bob", "carol")]

        held_lookup.held_user_id = "alice-id"
        late_peer = AsgiPeer()
        late_peer.disconnect()
        late_join = asyncio.create_task(matchmaking_websocket(_matchmaking_socket(app, late_peer, username="alice")))
        await held_lookup.started.wait()
        await matchmaking_websocket(_matchmaking_socket(app, AsgiPeer(), username="dave"))
        for _peer, handler in queued:
            await handler
        assert queued[0][0].received_json()[-1]["type"] == first_player_last_message

        held_lookup.release.set()
        await late_join
        assert late_peer.received_json() == [{"type": "error", "message": "already_in_game"}]
        assert app.state.matchmaking_manager.queue_size == 0

    async def test_matchmaking_websocket__when_another_task_closed_the_socket_mid_join__should_end_without_error(
        self, app, caplog
    ):
        peer = AsgiPeer()
        peer.send_gate = asyncio.Event()
        websocket = _matchmaking_socket(app, peer, username="late")
        handler = asyncio.create_task(matchmaking_websocket(websocket))
        await peer.send_waiting.wait()

        await websocket.close(code=4000, reason="match_failed")
        peer.send_gate.set()
        await handler
        assert "unexpected error in matchmaking websocket" not in caplog.text
        assert app.state.matchmaking_manager.queue_size == 0
