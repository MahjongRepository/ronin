from unittest.mock import patch

import pytest
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from game.logic.enums import GameAction
from game.logic.events import EventType
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server import websocket as ws_module
from game.server.app import _read_request_body, create_app
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.helpers.session import make_session_manager
from game.tests.helpers.websocket import (
    create_pending_game,
    join_game_and_start,
    recv_ws,
    send_ws,
)
from game.tests.mocks import MOCK_AWAITING, MockGameService
from game.wire.events import EVENT_TYPE_INT

ACTION_OUTSIDE_A_GAME = {"t": WireClientMessageType.GAME_ACTION, "wi": 0, "a": WireGameAction.PASS}


class TestWebSocketIntegration:
    @pytest.fixture
    def client(self):
        game_service = MockGameService()
        app = create_app(
            game_service=game_service,
            session_manager=make_session_manager(game_service),
        )
        with TestClient(app) as client:
            yield client

    def test_websocket__when_single_player_joins__should_start_game(self, client):
        tickets = create_pending_game(client, game_id="test_game")
        with client.websocket_connect("/ws/test_game") as ws:
            messages = join_game_and_start(ws, tickets[0])
            assert [message["t"] for message in messages] == [
                EVENT_TYPE_INT[EventType.GAME_STARTED],
                EVENT_TYPE_INT[EventType.ROUND_STARTED],
            ]

    def test_websocket__when_discard_sent__should_return_successful_draw_event(self, client):
        tickets = create_pending_game(client, game_id="test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            join_game_and_start(ws, tickets[0])

            send_ws(
                ws,
                {
                    "t": WireClientMessageType.GAME_ACTION,
                    "wi": MOCK_AWAITING.wait_id,
                    "a": WireGameAction.DISCARD,
                    "ti": 0,
                },
            )
            response = recv_ws(ws)
            assert response["t"] == EVENT_TYPE_INT[EventType.DRAW]
            assert response["seat"] == 0
            assert response["action"] == GameAction.DISCARD
            assert response["success"] is True

    def test_websocket__when_msgpack_invalid__should_return_error_and_keep_connection(self, client):
        tickets = create_pending_game(client, game_id="test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            # Send garbage bytes that aren't valid MessagePack
            ws.send_bytes(b"\xff\xff\xff")
            response = recv_ws(ws)
            assert response["type"] == SessionMessageType.ERROR
            assert response["code"] == SessionErrorCode.INVALID_MESSAGE

            # Connection should still be alive - verify by sending a valid join
            send_ws(
                ws,
                {"t": WireClientMessageType.JOIN_GAME, "game_ticket": tickets[0]},
            )
            msg = recv_ws(ws)
            assert msg["t"] == EVENT_TYPE_INT[EventType.GAME_STARTED]

    def test_websocket__when_join_ticket_invalid__should_return_invalid_ticket_error(self, client):
        create_pending_game(client, game_id="test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            send_ws(
                ws,
                {"t": WireClientMessageType.JOIN_GAME, "game_ticket": "not-a-valid-ticket"},
            )
            response = recv_ws(ws)
            assert response["type"] == SessionMessageType.ERROR
            assert response["code"] == SessionErrorCode.INVALID_TICKET

    def test_websocket__when_client_sends_a_text_frame__should_count_a_decode_strike_and_keep_connection(self, client):
        with client.websocket_connect("/ws/test_game") as ws:
            ws.send_text("not a binary frame")
            response = recv_ws(ws)
            assert response["type"] == SessionMessageType.ERROR
            assert response["code"] == SessionErrorCode.INVALID_MESSAGE

            send_ws(ws, ACTION_OUTSIDE_A_GAME)
            assert recv_ws(ws)["code"] == SessionErrorCode.NOT_IN_GAME

    def test_websocket__when_game_id_invalid__should_reject_before_accept(self, client):
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/invalid game!"):
            pass

    def test_websocket__when_decode_errors_hit_limit__should_disconnect(self, client):
        with patch.object(ws_module, "_MAX_DECODE_ERRORS", 3), client.websocket_connect("/ws/test_game") as ws:
            for _ in range(3):
                ws.send_bytes(b"\xff\xff\xff")
                recv_ws(ws)  # drain INVALID_MESSAGE error

            # Server closed the connection after 3 decode errors
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_bytes()
            assert (closed.value.code, closed.value.reason) == (4004, "too_many_decode_errors")

    def test_websocket__when_valid_message_follows_decode_errors__should_reset_error_counter(self, client):
        with patch.object(ws_module, "_MAX_DECODE_ERRORS", 3), client.websocket_connect("/ws/test_game") as ws:
            # Send 2 bad messages (below threshold)
            for _ in range(2):
                ws.send_bytes(b"\xff\xff\xff")
                resp = recv_ws(ws)
                assert resp["code"] == SessionErrorCode.INVALID_MESSAGE

            send_ws(ws, ACTION_OUTSIDE_A_GAME)
            resp = recv_ws(ws)
            assert resp["code"] == SessionErrorCode.NOT_IN_GAME

            # Send 2 more bad messages - should still be under threshold
            for _ in range(2):
                ws.send_bytes(b"\xff\xff\xff")
                resp = recv_ws(ws)
                assert resp["code"] == SessionErrorCode.INVALID_MESSAGE

    def test_websocket__when_burst_exceeded__should_return_rate_limited_error(self, client):
        with (
            patch.object(ws_module, "_RATE_LIMIT_BURST", 2),
            patch.object(ws_module, "_RATE_LIMIT_RATE", 0.0),
            client.websocket_connect("/ws/test_game") as ws,
        ):
            ws.send_bytes(b"\xff\xff\xff")
            assert recv_ws(ws)["code"] == SessionErrorCode.INVALID_MESSAGE
            send_ws(ws, ACTION_OUTSIDE_A_GAME)
            assert recv_ws(ws)["code"] == SessionErrorCode.NOT_IN_GAME

            send_ws(ws, ACTION_OUTSIDE_A_GAME)
            assert recv_ws(ws)["code"] == SessionErrorCode.RATE_LIMITED

    def test_websocket__when_malformed_after_burst_exhausted__should_drop_replies_and_disconnect_on_decode_strikes(
        self, client
    ):
        with (
            patch.object(ws_module, "_RATE_LIMIT_BURST", 2),
            patch.object(ws_module, "_RATE_LIMIT_RATE", 0.0),
            patch.object(ws_module, "_MAX_DECODE_ERRORS", 4),
            client.websocket_connect("/ws/test_game") as ws,
        ):
            for _ in range(2):
                send_ws(ws, ACTION_OUTSIDE_A_GAME)
                recv_ws(ws)

            for _ in range(4):
                ws.send_bytes(b"\xff\xff\xff")

            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_bytes()
            assert (closed.value.code, closed.value.reason) == (4004, "too_many_decode_errors")


class TestHealthEndpoint:
    @pytest.fixture
    def client(self):
        game_service = MockGameService()
        app = create_app(
            game_service=game_service,
            session_manager=make_session_manager(game_service),
        )
        with TestClient(app) as client:
            yield client

    def test_health_endpoint__should_return_ok_with_version_and_commit(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "commit" in data


class TestStatusEndpoint:
    @pytest.fixture
    def client(self):
        game_service = MockGameService()
        app = create_app(
            game_service=game_service,
            session_manager=make_session_manager(game_service),
        )
        with TestClient(app) as client:
            yield client

    def test_status_endpoint__when_no_games__should_return_zero_counts_and_capacity(self, client):
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["pending_games"] == 0
        assert data["active_games"] == 0
        assert data["capacity_used"] == 0
        assert data["max_capacity"] == 100
        assert "version" in data
        assert "commit" in data

    def test_status_endpoint__when_game_pending__should_count_it_as_pending(self, client):
        create_pending_game(client, game_id="room1")

        response = client.get("/status")
        data = response.json()
        assert data["pending_games"] == 1
        assert data["active_games"] == 0
        assert data["capacity_used"] == 1


class TestCreateGameEndpoint:
    @pytest.fixture
    def client(self):
        game_service = MockGameService()
        app = create_app(
            game_service=game_service,
            session_manager=make_session_manager(game_service),
        )
        with TestClient(app) as client:
            yield client

    def test_create_game_endpoint__when_body_valid__should_return_201_pending(self, client):
        ticket = make_test_game_ticket(username="Player1", room_id="test-game", user_id="user-0")

        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "players": [{"name": "Player1", "user_id": "user-0", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 201
        assert response.json() == {"game_id": "test-game", "status": "pending"}

    def test_create_game_endpoint__when_body_not_json__should_return_400(self, client):
        response = client.post("/games", content=b"not json")
        assert response.status_code == 400
        assert response.json() == {"error": "Invalid request body"}

    def test_create_game_endpoint__when_game_id_invalid__should_return_400(self, client):
        ticket = make_test_game_ticket(username="Player1", room_id="bad id!", user_id="user-0")

        response = client.post(
            "/games",
            json={
                "game_id": "bad id!",
                "players": [{"name": "Player1", "user_id": "user-0", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 400
        assert response.json() == {"error": "Invalid request body"}

    def test_create_game_endpoint__when_pending_game_exists__should_return_409(self, client):
        create_pending_game(client, game_id="dupe")
        ticket = make_test_game_ticket(username="Player5", room_id="dupe", user_id="user-5")

        response = client.post(
            "/games",
            json={
                "game_id": "dupe",
                "players": [{"name": "Player5", "user_id": "user-5", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 409
        assert response.json() == {"error": "Game with this ID already exists"}

    def test_create_game_endpoint__when_a_player_is_already_playing__should_report_the_game_and_return_409(
        self, client
    ):
        create_pending_game(client, game_id="first")
        ticket = make_test_game_ticket(username="Player1", room_id="second", user_id="user-0")

        response = client.post(
            "/games",
            json={
                "game_id": "second",
                "players": [{"name": "Player1", "user_id": "user-0", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 409
        assert response.json() == {"error": "Player already in a game"}
        assert client.get("/players/user-0").json() == {"game_id": "first"}
        assert client.get("/players/user-9").status_code == 404

    def test_create_game_endpoint__when_server_at_capacity__should_return_503(self, client):
        for i in range(100):
            ticket = make_test_game_ticket(username=f"P{i}", room_id=f"room{i}", user_id=f"u-{i}")
            resp = client.post(
                "/games",
                json={
                    "game_id": f"room{i}",
                    "players": [{"name": f"P{i}", "user_id": f"u-{i}", "game_ticket": ticket}],
                },
            )
            assert resp.status_code == 201

        ticket = make_test_game_ticket(username="Poverflow", room_id="overflow", user_id="u-overflow")
        response = client.post(
            "/games",
            json={
                "game_id": "overflow",
                "players": [{"name": "Poverflow", "user_id": "u-overflow", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 503
        assert response.json() == {"error": "Server at capacity"}

    def test_create_game_endpoint__when_body_oversized__should_return_413(self, client):
        oversized = b'{"game_id": "' + b"x" * 5000 + b'"}'

        response = client.post("/games", content=oversized, headers={"Content-Type": "application/json"})
        assert response.status_code == 413
        assert response.json() == {"error": "Request body too large"}


class TestReadRequestBodyClientDisconnect:
    async def test_read_request_body__when_client_disconnects__should_return_400(self):
        class DisconnectingRequest:
            async def stream(self):
                yield b"partial"
                raise ClientDisconnect

        result = await _read_request_body(DisconnectingRequest())
        assert isinstance(result, JSONResponse)
        assert result.status_code == 400
