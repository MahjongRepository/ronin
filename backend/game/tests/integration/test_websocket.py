"""Integration tests for WebSocket and HTTP endpoints.

These tests verify the web/transport layer (HTTP endpoints, WebSocket protocol,
MessagePack encoding) using the test client. They complement the game logic
Replay tests by ensuring the service layer works correctly.
"""

from unittest.mock import patch

import pytest
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from game.logic.enums import GameAction
from game.logic.events import EventType
from game.messaging.event_payload import EVENT_TYPE_INT
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server import websocket as ws_module
from game.server.app import _read_request_body, create_app
from game.session.manager import SessionManager
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.helpers.websocket import (
    create_pending_game,
    join_game_and_start,
    recv_ws,
    send_ws,
)
from game.tests.mocks import MockGameService


class TestWebSocketIntegration:
    @pytest.fixture
    def client(self):
        game_service = MockGameService()
        app = create_app(game_service=game_service, session_manager=SessionManager(game_service))
        with TestClient(app) as client:
            yield client

    def test_join_game_and_start(self, client):
        tickets = create_pending_game(client, "test_game")
        with client.websocket_connect("/ws/test_game") as ws:
            messages = join_game_and_start(ws, tickets[0])
            last = messages[-1]
            assert last["t"] in (EVENT_TYPE_INT[EventType.ROUND_STARTED], EVENT_TYPE_INT[EventType.DRAW])

    def test_game_chat_message(self, client):
        """Chat messages in a started game are broadcast to game players."""
        tickets = create_pending_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            join_game_and_start(ws, tickets[0])

            send_ws(ws, {"t": WireClientMessageType.CHAT, "text": "Hello from game!"})

            response = recv_ws(ws)
            assert response["type"] == SessionMessageType.CHAT
            assert response["player_name"] == "Player1"
            assert response["text"] == "Hello from game!"

    def test_game_action(self, client):
        tickets = create_pending_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            join_game_and_start(ws, tickets[0])

            send_ws(ws, {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": 0})

            response = recv_ws(ws)
            assert response["t"] == EVENT_TYPE_INT[EventType.DRAW]
            assert response["player"] == "Player1"
            assert response["action"] == GameAction.DISCARD
            assert response["success"] is True

    def test_invalid_msgpack_returns_error_and_keeps_connection(self, client):
        """Sending invalid MessagePack data returns an error without disconnecting."""
        tickets = create_pending_game(client, "test_game")

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
            # Should get game events (not an error about dead connection)
            msg = recv_ws(ws)
            assert msg.get("t") is not None or msg.get("type") is not None

    def test_join_game_with_invalid_ticket(self, client):
        """An invalid game ticket returns an INVALID_TICKET error."""
        create_pending_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            send_ws(
                ws,
                {"t": WireClientMessageType.JOIN_GAME, "game_ticket": "not-a-valid-ticket"},
            )

            response = recv_ws(ws)
            assert response["type"] == SessionMessageType.ERROR
            assert response["code"] == SessionErrorCode.INVALID_TICKET

    def test_invalid_game_id_rejected_before_accept(self, client):
        """WebSocket connection with invalid game_id is rejected before accept."""
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/invalid game!"):
            pass

    def test_repeated_decode_errors_disconnect(self, client):
        """Sending too many consecutive malformed messages disconnects the client."""
        with patch.object(ws_module, "_MAX_DECODE_ERRORS", 3), client.websocket_connect("/ws/test_game") as ws:
            for _ in range(3):
                ws.send_bytes(b"\xff\xff\xff")
                recv_ws(ws)  # drain INVALID_MESSAGE error
            # Server closed the connection after 3 decode errors
            with pytest.raises(WebSocketDisconnect):
                ws.receive_bytes()

    def test_decode_error_counter_resets_on_valid_message(self, client):
        """A valid message resets the decode error counter."""
        with patch.object(ws_module, "_MAX_DECODE_ERRORS", 3), client.websocket_connect("/ws/test_game") as ws:
            # Send 2 bad messages (below threshold)
            for _ in range(2):
                ws.send_bytes(b"\xff\xff\xff")
                resp = recv_ws(ws)
                assert resp["code"] == SessionErrorCode.INVALID_MESSAGE

            # Send a valid PING to reset the counter
            send_ws(ws, {"t": WireClientMessageType.PING})
            resp = recv_ws(ws)
            assert resp["type"] == SessionMessageType.PONG

            # Send 2 more bad messages - should still be under threshold
            for _ in range(2):
                ws.send_bytes(b"\xff\xff\xff")
                resp = recv_ws(ws)
                assert resp["code"] == SessionErrorCode.INVALID_MESSAGE

    def test_rate_limited_message_returns_error(self, client):
        """Flooding valid messages produces RATE_LIMITED error responses."""
        with (
            patch.object(ws_module, "_RATE_LIMIT_BURST", 2),
            patch.object(ws_module, "_RATE_LIMIT_RATE", 1.0),
            client.websocket_connect("/ws/test_game") as ws,
        ):
            # First 2 valid messages consume burst
            for _ in range(2):
                send_ws(ws, {"t": WireClientMessageType.PING})
                recv_ws(ws)  # PONG responses

            # Next valid message should be rate-limited
            send_ws(ws, {"t": WireClientMessageType.PING})
            resp = recv_ws(ws)
            assert resp["code"] == SessionErrorCode.RATE_LIMITED

    def test_malformed_messages_count_strikes_when_rate_limited(self, client):
        """Malformed messages increment decode errors even when the bucket is drained."""
        with (
            patch.object(ws_module, "_RATE_LIMIT_BURST", 2),
            patch.object(ws_module, "_RATE_LIMIT_RATE", 1.0),
            patch.object(ws_module, "_MAX_DECODE_ERRORS", 4),
            client.websocket_connect("/ws/test_game") as ws,
        ):
            # Drain the bucket with valid messages
            for _ in range(2):
                send_ws(ws, {"t": WireClientMessageType.PING})
                recv_ws(ws)

            # Send malformed messages - they hit decode (not rate-limit) and
            # accumulate strikes until disconnect
            for _ in range(4):
                ws.send_bytes(b"\xff\xff\xff")
                resp = recv_ws(ws)
                assert resp["code"] == SessionErrorCode.INVALID_MESSAGE

            with pytest.raises(WebSocketDisconnect):
                ws.receive_bytes()


class TestHealthEndpoint:
    @pytest.fixture
    def client(self):
        game_service = MockGameService()
        app = create_app(game_service=game_service, session_manager=SessionManager(game_service))
        with TestClient(app) as client:
            yield client

    def test_health_returns_ok(self, client):
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
        app = create_app(game_service=game_service, session_manager=SessionManager(game_service))
        with TestClient(app) as client:
            yield client

    def test_status_returns_game_info(self, client):
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

    def test_status_reflects_pending_games(self, client):
        create_pending_game(client, "r1")
        response = client.get("/status")
        data = response.json()
        assert data["pending_games"] == 1
        assert data["active_games"] == 0
        assert data["capacity_used"] == 1


class TestCreateGameEndpoint:
    @pytest.fixture
    def client(self):
        game_service = MockGameService()
        app = create_app(game_service=game_service, session_manager=SessionManager(game_service))
        with TestClient(app) as client:
            yield client

    def test_create_game_success(self, client):
        ticket = make_test_game_ticket("Player1", "test-game", user_id="user-0")
        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "players": [{"name": "Player1", "user_id": "user-0", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 201
        assert response.json() == {"game_id": "test-game", "status": "pending"}

    def test_create_game_invalid_body(self, client):
        response = client.post("/games", content=b"not json")
        assert response.status_code == 400
        assert response.json() == {"error": "Invalid request body"}

    def test_create_game_invalid_game_id(self, client):
        ticket = make_test_game_ticket("Player1", "bad id!", user_id="user-0")
        response = client.post(
            "/games",
            json={
                "game_id": "bad id!",
                "players": [{"name": "Player1", "user_id": "user-0", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 400
        assert response.json() == {"error": "Invalid request body"}

    def test_create_game_duplicate(self, client):
        create_pending_game(client, "dupe")
        ticket = make_test_game_ticket("Player1", "dupe", user_id="user-0")
        response = client.post(
            "/games",
            json={
                "game_id": "dupe",
                "players": [{"name": "Player1", "user_id": "user-0", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 409
        assert response.json() == {"error": "Game with this ID already exists"}

    def test_create_game_conflicts_with_active_game(self, client):
        sm = client.app.state.session_manager
        sm._games["active-game"] = object()
        ticket = make_test_game_ticket("Player1", "active-game", user_id="user-0")
        response = client.post(
            "/games",
            json={
                "game_id": "active-game",
                "players": [{"name": "Player1", "user_id": "user-0", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 409
        assert response.json() == {"error": "Game with this ID already exists"}

    def test_create_game_at_capacity(self, client):
        for i in range(100):
            ticket = make_test_game_ticket(f"P{i}", f"r{i}", user_id=f"u-{i}")
            resp = client.post(
                "/games",
                json={
                    "game_id": f"r{i}",
                    "players": [{"name": f"P{i}", "user_id": f"u-{i}", "game_ticket": ticket}],
                },
            )
            assert resp.status_code == 201
        ticket = make_test_game_ticket("Poverflow", "overflow", user_id="u-overflow")
        response = client.post(
            "/games",
            json={
                "game_id": "overflow",
                "players": [{"name": "Poverflow", "user_id": "u-overflow", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 503
        assert response.json() == {"error": "Server at capacity"}

    def test_create_game_oversized_body_rejected(self, client):
        oversized = b'{"game_id": "' + b"x" * 5000 + b'"}'
        response = client.post("/games", content=oversized, headers={"Content-Type": "application/json"})
        assert response.status_code == 413
        assert response.json() == {"error": "Request body too large"}


class TestReadRequestBodyClientDisconnect:
    """Unit-level test for the _read_request_body ClientDisconnect path."""

    async def test_client_disconnect_returns_400(self):
        class DisconnectingRequest:
            async def stream(self):
                yield b"partial"
                raise ClientDisconnect

        result = await _read_request_body(DisconnectingRequest())
        assert isinstance(result, JSONResponse)
        assert result.status_code == 400
