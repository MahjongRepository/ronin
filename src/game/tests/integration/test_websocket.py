"""Integration tests for WebSocket and HTTP endpoints.

These tests verify the web/transport layer (HTTP endpoints, WebSocket protocol,
MessagePack encoding) using the test client. They complement the game logic
Replay tests by ensuring the service layer works correctly.
"""

import pytest
from starlette.testclient import TestClient

from game.logic.enums import GameAction
from game.logic.events import EventType
from game.messaging.encoder import decode, encode
from game.messaging.types import ClientMessageType, SessionMessageType
from game.server.app import create_app
from game.tests.mocks import MockGameService


class TestWebSocketIntegration:
    @pytest.fixture
    def client(self):
        # use MockGameService for predictable test behavior
        app = create_app(game_service=MockGameService())
        return TestClient(app)

    def _create_game(self, client, game_id: str, num_bots: int = 3) -> dict:
        response = client.post("/games", json={"game_id": game_id, "num_bots": num_bots})
        assert response.status_code == 201
        return response.json()

    def _send_message(self, ws, data: dict) -> None:
        """
        Send a MessagePack-encoded message over WebSocket.
        """
        ws.send_bytes(encode(data))

    def _receive_message(self, ws) -> dict:
        """
        Receive and decode a MessagePack message from WebSocket.
        """
        return decode(ws.receive_bytes())

    def test_connect_and_join_game(self, client):
        self._create_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            self._send_message(
                ws,
                {
                    "type": ClientMessageType.JOIN_GAME,
                    "game_id": "test_game",
                    "player_name": "TestPlayer",
                    "session_token": "tok-test-1",
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == SessionMessageType.GAME_JOINED
            assert response["game_id"] == "test_game"
            assert response["players"] == ["TestPlayer"]
            assert "session_token" in response
            assert isinstance(response["session_token"], str)

    def test_chat_message(self, client):
        self._create_game(client, "test_game", num_bots=2)

        with client.websocket_connect("/ws/test_game") as ws1:
            self._send_message(
                ws1,
                {
                    "type": ClientMessageType.JOIN_GAME,
                    "game_id": "test_game",
                    "player_name": "Player1",
                    "session_token": "tok-chat-1",
                },
            )
            self._receive_message(ws1)  # game_joined

            with client.websocket_connect("/ws/test_game") as ws2:
                self._send_message(
                    ws2,
                    {
                        "type": ClientMessageType.JOIN_GAME,
                        "game_id": "test_game",
                        "player_name": "Player2",
                        "session_token": "tok-chat-2",
                    },
                )
                self._receive_message(ws2)  # game_joined
                self._receive_message(ws1)  # player_joined

                # drain game_started and round_started events
                self._receive_message(ws1)  # game_started
                self._receive_message(ws1)  # round_started for seat_0
                self._receive_message(ws2)  # game_started

                # Player1 sends chat
                self._send_message(
                    ws1,
                    {
                        "type": ClientMessageType.CHAT,
                        "text": "Hello!",
                    },
                )

                # Both players receive the chat
                chat1 = self._receive_message(ws1)
                chat2 = self._receive_message(ws2)

                assert chat1["type"] == SessionMessageType.CHAT
                assert chat1["player_name"] == "Player1"
                assert chat1["text"] == "Hello!"
                assert chat2 == chat1

    def test_game_action(self, client):
        self._create_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            self._send_message(
                ws,
                {
                    "type": ClientMessageType.JOIN_GAME,
                    "game_id": "test_game",
                    "player_name": "Player1",
                    "session_token": "tok-action-1",
                },
            )
            self._receive_message(ws)  # game_joined
            self._receive_message(ws)  # game_started event (broadcast)
            self._receive_message(ws)  # round_started event for seat_0

            self._send_message(
                ws,
                {
                    "type": ClientMessageType.GAME_ACTION,
                    "action": GameAction.DISCARD,
                    "data": {"foo": "bar"},
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == EventType.DRAW
            assert response["player"] == "Player1"
            assert response["action"] == GameAction.DISCARD
            assert response["success"] is True

    def test_list_games_empty(self, client):
        response = client.get("/games")
        assert response.status_code == 200
        data = response.json()
        assert data == {"games": []}


class TestHealthEndpoint:
    @pytest.fixture
    def client(self):
        app = create_app(game_service=MockGameService())
        return TestClient(app)

    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestStatusEndpoint:
    @pytest.fixture
    def client(self):
        app = create_app(game_service=MockGameService())
        return TestClient(app)

    def test_status_returns_game_info(self, client):
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "ok", "active_games": 0, "max_games": 100}

    def test_status_reflects_active_games(self, client):
        client.post("/games", json={"game_id": "g1"})
        response = client.get("/status")
        data = response.json()
        assert data["active_games"] == 1


class TestCreateGameEndpoint:
    @pytest.fixture
    def client(self):
        app = create_app(game_service=MockGameService())
        return TestClient(app)

    def test_create_game_success(self, client):
        response = client.post("/games", json={"game_id": "test-game"})
        assert response.status_code == 201
        assert response.json() == {"game_id": "test-game", "num_bots": 3, "status": "created"}

    def test_create_game_invalid_body(self, client):
        response = client.post("/games", content=b"not json")
        assert response.status_code == 400

    def test_create_game_invalid_game_id(self, client):
        response = client.post("/games", json={"game_id": "bad id!"})
        assert response.status_code == 400

    def test_create_game_duplicate(self, client):
        client.post("/games", json={"game_id": "dupe"})
        response = client.post("/games", json={"game_id": "dupe"})
        assert response.status_code == 409
        assert response.json() == {"error": "Game already exists"}

    def test_create_game_with_custom_num_bots(self, client):
        response = client.post("/games", json={"game_id": "mixed-game", "num_bots": 2})
        assert response.status_code == 201
        assert response.json() == {"game_id": "mixed-game", "num_bots": 2, "status": "created"}

    def test_create_game_with_zero_bots(self, client):
        response = client.post("/games", json={"game_id": "pvp-game", "num_bots": 0})
        assert response.status_code == 201
        assert response.json() == {"game_id": "pvp-game", "num_bots": 0, "status": "created"}

    def test_create_game_invalid_num_bots(self, client):
        response = client.post("/games", json={"game_id": "bad-game", "num_bots": 5})
        assert response.status_code == 400

    def test_list_games_shows_num_bots(self, client):
        client.post("/games", json={"game_id": "bot-game", "num_bots": 3})
        client.post("/games", json={"game_id": "mixed-game", "num_bots": 1})

        response = client.get("/games")
        assert response.status_code == 200
        games = {g["game_id"]: g for g in response.json()["games"]}
        assert games["bot-game"]["num_bots"] == 3
        assert games["mixed-game"]["num_bots"] == 1

    def test_create_game_at_capacity(self, client):
        # create MAX_GAMES games to fill capacity
        for i in range(100):
            resp = client.post("/games", json={"game_id": f"g{i}"})
            assert resp.status_code == 201
        response = client.post("/games", json={"game_id": "overflow"})
        assert response.status_code == 503
        assert response.json() == {"error": "Server at capacity"}
