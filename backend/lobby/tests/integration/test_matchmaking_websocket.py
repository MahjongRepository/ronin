import asyncio
import json

import httpx
import pytest
from starlette.websockets import WebSocketDisconnect

from lobby.auth.models import AuthenticatedPlayer
from lobby.matchmaking.websocket import matchmaking_websocket
from lobby.tests.conftest import AsgiPeer, HeldLookup, make_websocket
from lobby.tests.integration.conftest import register_with_csrf
from shared.auth.game_ticket import verify_game_ticket


def _time_out_after_the_game_server_got_the_request(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("read timed out after the game server got the request", request=request)


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
    def client(self, client):
        register_with_csrf(client, "player1")
        return client

    def test_matchmaking_websocket__when_authenticated_client_connects__should_send_queue_joined(self, client):
        with client.websocket_connect("/ws/matchmaking") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "queue_joined"
            assert msg["queue_size"] == 1
            assert msg["position"] == 1

    async def test_matchmaking_websocket__when_client_sends_frames__should_discard_them_unanswered(self, app):
        peer = AsgiPeer()
        peer.send_from_client(json.dumps({"type": "ping"}))
        peer.send_bytes_from_client(b"\x81")
        peer.disconnect()

        await matchmaking_websocket(_matchmaking_socket(app, peer, username="alice"))
        assert [message["type"] for message in peer.received_json()] == ["queue_joined"]
        assert app.state.matchmaking_manager.queue_size == 0

    def test_matchmaking_websocket__when_client_disconnects__should_remove_from_queue(self, app, client):
        with client.websocket_connect("/ws/matchmaking"):
            assert app.state.matchmaking_manager.queue_size == 1
        assert app.state.matchmaking_manager.queue_size == 0

    async def test_matchmaking_websocket__when_queued_user_connects_again__should_hand_the_entry_to_the_new_socket(
        self, app
    ):
        old_peer, old_handler = await _queue_player(app, "alice")
        others = [await _queue_player(app, username) for username in ("bob", "carol")]
        bob_peer = others[0][0]

        new_peer, new_handler = await _queue_player(app, "alice")
        await old_handler
        assert new_peer.received_json() == [{"type": "queue_joined", "position": 1, "queue_size": 3}]
        assert old_peer.received_json()[-1] == {"type": "error", "message": "replaced_by_new_connection"}
        assert old_peer.close_codes() == [4000]
        assert [message["type"] for message in bob_peer.received_json()] == ["queue_joined", "queue_update"]
        queued_usernames = [player.username for player in app.state.matchmaking_manager.get_queued_players()]
        assert queued_usernames == ["alice", "bob", "carol"]

        new_peer.disconnect()
        await new_handler
        queued_usernames = [player.username for player in app.state.matchmaking_manager.get_queued_players()]
        assert queued_usernames == ["bob", "carol"]

        for peer, handler in others:
            peer.disconnect()
            await handler

    async def test_matchmaking_websocket__when_user_is_playing__should_reject_with_already_in_game(
        self, make_app, caplog
    ):
        async def alice_playing(user_id):
            return user_id == "alice-id"

        app = make_app(is_playing=alice_playing)
        bob_peer, bob_handler = await _queue_player(app, "bob")

        peer = AsgiPeer()
        await matchmaking_websocket(_matchmaking_socket(app, peer, username="alice"))
        assert peer.received_json() == [{"type": "error", "message": "already_in_game"}]
        assert peer.close_codes() == [4000]
        assert app.state.matchmaking_manager.queue_size == 1
        assert [message["type"] for message in bob_peer.received_json()] == ["queue_joined"]
        assert "player left matchmaking queue" not in caplog.text

        bob_peer.disconnect()
        await bob_handler

    def test_matchmaking_websocket__when_already_in_room__should_send_error_naming_the_room(self, app, client):
        room = app.state.room_manager.create_room("test-room")
        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_room:
            ws_room.receive_json()
            with client.websocket_connect("/ws/matchmaking") as ws_mm:
                assert ws_mm.receive_json() == {"type": "error", "message": "already_in_room", "room_id": "test-room"}


class TestMatchmakingUnauthenticated:
    def test_matchmaking_websocket__when_unauthenticated__should_close_with_4001(self, client):
        with pytest.raises(WebSocketDisconnect) as rejection, client.websocket_connect("/ws/matchmaking"):
            pass
        assert rejection.value.code == 4001


class TestMatchmakingOriginCheck:
    def test_matchmaking_websocket__when_origin_forbidden__should_close_with_4003(self, client):
        register_with_csrf(client, "player1")
        with (
            pytest.raises(WebSocketDisconnect) as rejection,
            client.websocket_connect("/ws/matchmaking", headers={"origin": "http://evil.com"}),
        ):
            pass
        assert rejection.value.code == 4003


class TestMatchmakingGameTransition:
    async def test_matchmaking_websocket__when_game_creation_fails__should_close_all_four_and_let_them_queue_again(
        self, app, game_server
    ):
        game_server.respond = _time_out_after_the_game_server_got_the_request
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

    async def test_matchmaking_websocket__when_a_matched_peer_is_held__should_start_the_game_for_the_rest(
        self, app, game_server
    ):
        created_game_ids: list[str] = []

        def create_game(request: httpx.Request) -> httpx.Response:
            created_game_ids.append(json.loads(request.content)["game_id"])
            return httpx.Response(201)

        game_server.respond = create_game
        queued = [await _queue_player(app, f"queued-{i}") for i in range(3)]
        held_peer, held_handler = queued[0]
        held_peer.send_gate = asyncio.Event()
        fourth_peer = AsgiPeer()

        await matchmaking_websocket(_matchmaking_socket(app, fourth_peer, username="fourth"))
        for _peer, handler in queued[1:]:
            await handler
        healthy_peers = {"queued-1": queued[1][0], "queued-2": queued[2][0], "fourth": fourth_peer}
        for username, peer in healthy_peers.items():
            game_starting = peer.received_json()[-1]
            ticket = verify_game_ticket(game_starting["game_ticket"], "test-secret")
            assert game_starting["type"] == "game_starting"
            assert [game_starting["game_id"]] == created_game_ids
            assert ticket is not None
            assert ticket.username == username
            assert peer.close_codes() == [1000]
        assert "game_starting" not in [message["type"] for message in held_peer.received_json()]

        held_peer.send_gate.set()
        await held_handler
        assert held_peer.received_json()[-1]["type"] == "game_starting"
        assert held_peer.close_codes() == [1000]
        assert app.state.matchmaking_manager.queue_size == 0

    async def test_matchmaking_websocket__when_a_matched_user_connects_again__should_reject_with_match_starting(
        self, app, game_server
    ):
        creation_requested = asyncio.Event()
        creation_released = asyncio.Event()

        async def held_creation(_request: httpx.Request) -> httpx.Response:
            creation_requested.set()
            await creation_released.wait()
            return httpx.Response(201)

        game_server.respond = held_creation
        queued = [await _queue_player(app, username) for username in ("alice", "bob", "carol")]
        completing_join = asyncio.create_task(
            matchmaking_websocket(_matchmaking_socket(app, AsgiPeer(), username="dave"))
        )
        await creation_requested.wait()

        rejoining_peer = AsgiPeer()
        await matchmaking_websocket(_matchmaking_socket(app, rejoining_peer, username="alice"))
        assert rejoining_peer.received_json() == [{"type": "error", "message": "match_starting"}]
        assert rejoining_peer.close_codes() == [4000]

        creation_released.set()
        await completing_join
        for peer, handler in queued:
            await handler
            assert peer.received_json()[-1]["type"] == "game_starting"

    @pytest.mark.parametrize(
        ("create_game", "first_player_last_message"),
        [
            (lambda _request: httpx.Response(201), "game_starting"),
            (_time_out_after_the_game_server_got_the_request, "error"),
        ],
        ids=["created", "creation_failed_after_the_game_server_got_it"],
    )
    async def test_matchmaking_websocket__when_a_match_starts_during_the_lookup__should_reject_with_already_in_game(
        self, make_app, game_server, create_game, first_player_last_message
    ):
        held_lookup = HeldLookup()
        app = make_app(is_playing=held_lookup)
        game_server.respond = create_game
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
