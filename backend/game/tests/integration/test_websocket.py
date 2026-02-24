"""Integration tests for WebSocket and HTTP endpoints.

These tests verify the web/transport layer (HTTP endpoints, WebSocket protocol,
MessagePack encoding) using the test client. They complement the game logic
Replay tests by ensuring the service layer works correctly.
"""

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from game.logic.enums import GameAction, WireClientMessageType, WireGameAction
from game.logic.events import EventType
from game.messaging.encoder import decode, encode
from game.messaging.event_payload import EVENT_TYPE_INT
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.server.app import create_app
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.mocks import MockGameService


def _create_pending_game(client, game_id: str, num_ai_players: int = 3) -> list[str]:
    """Create a pending game via POST /games. Return the list of game tickets."""
    num_humans = 4 - num_ai_players
    players = []
    tickets = []
    for i in range(num_humans):
        ticket = make_test_game_ticket(f"Player{i + 1}", game_id, user_id=f"user-{i}")
        players.append({"name": f"Player{i + 1}", "user_id": f"user-{i}", "game_ticket": ticket})
        tickets.append(ticket)
    response = client.post(
        "/games",
        json={"game_id": game_id, "players": players, "num_ai_players": num_ai_players},
    )
    assert response.status_code == 201
    return tickets


def _send(ws, data: dict) -> None:
    ws.send_bytes(encode(data))


def _recv(ws) -> dict:
    return decode(ws.receive_bytes())


def _join_game_and_start(ws, ticket: str) -> list[dict]:
    """Join a pending game via JOIN_GAME and drain startup messages."""
    _send(ws, {"t": WireClientMessageType.JOIN_GAME, "game_ticket": ticket})
    messages = []
    while True:
        msg = _recv(ws)
        messages.append(msg)
        if msg.get("t") in (EVENT_TYPE_INT[EventType.ROUND_STARTED], EVENT_TYPE_INT[EventType.DRAW]):
            break
    return messages


class TestWebSocketIntegration:
    @pytest.fixture
    def client(self):
        app = create_app(game_service=MockGameService())
        return TestClient(app)

    def test_join_game_and_start(self, client):
        tickets = _create_pending_game(client, "test_game")
        ticket = tickets[0]

        with client.websocket_connect("/ws/test_game") as ws:
            _send(ws, {"t": WireClientMessageType.JOIN_GAME, "game_ticket": ticket})
            messages = []
            while True:
                msg = _recv(ws)
                messages.append(msg)
                if msg.get("t") in (EVENT_TYPE_INT[EventType.ROUND_STARTED], EVENT_TYPE_INT[EventType.DRAW]):
                    break
            # Should have received game events
            assert len(messages) >= 1

    def test_game_chat_message(self, client):
        """Chat messages in a started game are broadcast to game players."""
        tickets = _create_pending_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            _join_game_and_start(ws, tickets[0])

            _send(ws, {"t": WireClientMessageType.CHAT, "text": "Hello from game!"})

            response = _recv(ws)
            assert response["type"] == SessionMessageType.CHAT
            assert response["player_name"] == "Player1"
            assert response["text"] == "Hello from game!"

    def test_game_action(self, client):
        tickets = _create_pending_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            _join_game_and_start(ws, tickets[0])

            _send(ws, {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": 0})

            response = _recv(ws)
            assert response["t"] == EVENT_TYPE_INT[EventType.DRAW]
            assert response["player"] == "Player1"
            assert response["action"] == GameAction.DISCARD
            assert response["success"] is True

    def test_invalid_msgpack_returns_error_and_keeps_connection(self, client):
        """Sending invalid MessagePack data returns an error without disconnecting."""
        tickets = _create_pending_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            # Send garbage bytes that aren't valid MessagePack
            ws.send_bytes(b"\xff\xff\xff")

            response = _recv(ws)
            assert response["type"] == SessionMessageType.ERROR
            assert response["code"] == SessionErrorCode.INVALID_MESSAGE

            # Connection should still be alive - verify by sending a valid join
            _send(
                ws,
                {"t": WireClientMessageType.JOIN_GAME, "game_ticket": tickets[0]},
            )
            # Should get game events (not an error about dead connection)
            msg = _recv(ws)
            assert msg.get("t") is not None or msg.get("type") is not None

    def test_join_game_with_invalid_ticket(self, client):
        """An invalid game ticket returns an INVALID_TICKET error."""
        _create_pending_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            _send(
                ws,
                {"t": WireClientMessageType.JOIN_GAME, "game_ticket": "not-a-valid-ticket"},
            )

            response = _recv(ws)
            assert response["type"] == SessionMessageType.ERROR
            assert response["code"] == SessionErrorCode.INVALID_TICKET

    def test_invalid_game_id_rejected_before_accept(self, client):
        """WebSocket connection with invalid game_id is rejected before accept."""
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/invalid game!"):
            pass


class TestHealthEndpoint:
    @pytest.fixture
    def client(self):
        app = create_app(game_service=MockGameService())
        return TestClient(app)

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
        app = create_app(game_service=MockGameService())
        return TestClient(app)

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
        _create_pending_game(client, "r1")
        response = client.get("/status")
        data = response.json()
        assert data["pending_games"] == 1
        assert data["active_games"] == 0
        assert data["capacity_used"] == 1


class TestCreateGameEndpoint:
    @pytest.fixture
    def client(self):
        app = create_app(game_service=MockGameService())
        return TestClient(app)

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
        _create_pending_game(client, "dupe")
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
