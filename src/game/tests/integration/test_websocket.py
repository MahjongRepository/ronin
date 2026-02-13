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

    def _create_room(self, client, room_id: str, num_bots: int = 3) -> None:
        session_manager = client.app.state.session_manager
        session_manager.create_room(room_id, num_bots=num_bots)

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

    def _join_room_and_ready(self, ws, room_id: str, player_name: str) -> list[dict]:
        """Join a room, ready up, and return all received messages."""
        self._send_message(
            ws,
            {
                "type": ClientMessageType.JOIN_ROOM,
                "room_id": room_id,
                "player_name": player_name,
                "session_token": "tok-test",
            },
        )
        messages = []
        # Drain: room_joined, player_ready_changed, game_starting, game events...
        messages.append(self._receive_message(ws))  # room_joined

        self._send_message(ws, {"type": ClientMessageType.SET_READY, "ready": True})
        # Drain remaining startup messages
        while True:
            msg = self._receive_message(ws)
            messages.append(msg)
            # Stop after we've received a game event (round_started or draw)
            if msg.get("type") in (EventType.ROUND_STARTED, EventType.DRAW):
                break
        return messages

    def test_connect_join_room_and_start_game(self, client):
        self._create_room(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            self._send_message(
                ws,
                {
                    "type": ClientMessageType.JOIN_ROOM,
                    "room_id": "test_game",
                    "player_name": "TestPlayer",
                    "session_token": "tok-test",
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == SessionMessageType.ROOM_JOINED
            assert response["room_id"] == "test_game"
            assert len(response["players"]) == 1
            assert response["players"][0]["name"] == "TestPlayer"

    def test_room_chat_message(self, client):
        """Chat messages in a room are broadcast to all room members."""
        self._create_room(client, "test_game", num_bots=2)

        with client.websocket_connect("/ws/test_game") as ws1:
            self._send_message(
                ws1,
                {
                    "type": ClientMessageType.JOIN_ROOM,
                    "room_id": "test_game",
                    "player_name": "Player1",
                    "session_token": "tok-p1",
                },
            )
            self._receive_message(ws1)  # room_joined

            with client.websocket_connect("/ws/test_game") as ws2:
                self._send_message(
                    ws2,
                    {
                        "type": ClientMessageType.JOIN_ROOM,
                        "room_id": "test_game",
                        "player_name": "Player2",
                        "session_token": "tok-p2",
                    },
                )
                self._receive_message(ws2)  # room_joined
                self._receive_message(ws1)  # player_joined(Player2)

                # Player1 sends chat while in the room
                self._send_message(
                    ws1,
                    {
                        "type": ClientMessageType.CHAT,
                        "text": "Hello!",
                    },
                )

                chat1 = self._receive_message(ws1)
                chat2 = self._receive_message(ws2)

                assert chat1["type"] == SessionMessageType.CHAT
                assert chat1["player_name"] == "Player1"
                assert chat1["text"] == "Hello!"
                assert chat2 == chat1

    def test_game_chat_message(self, client):
        """Chat messages in a started game are broadcast to game players."""
        self._create_room(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            self._join_room_and_ready(ws, "test_game", "Player1")

            self._send_message(
                ws,
                {
                    "type": ClientMessageType.CHAT,
                    "text": "Hello from game!",
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == SessionMessageType.CHAT
            assert response["player_name"] == "Player1"
            assert response["text"] == "Hello from game!"

    def test_game_action(self, client):
        self._create_room(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            self._join_room_and_ready(ws, "test_game", "Player1")

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

    def test_list_rooms_empty(self, client):
        response = client.get("/rooms")
        assert response.status_code == 200
        data = response.json()
        assert data == {"rooms": []}

    def test_join_room_injects_room_id_from_path(self, client):
        """WebSocket path param injects room_id into join_room messages."""
        self._create_room(client, "test-room", num_bots=2)

        with client.websocket_connect("/ws/test-room") as ws:
            # send join_room without room_id -- the endpoint should inject it
            self._send_message(
                ws,
                {
                    "type": ClientMessageType.JOIN_ROOM,
                    "room_id": "ignored",
                    "player_name": "TestPlayer",
                    "session_token": "tok-test",
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == SessionMessageType.ROOM_JOINED
            assert response["room_id"] == "test-room"


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

    def test_status_returns_room_and_game_info(self, client):
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "status": "ok",
            "active_rooms": 0,
            "active_games": 0,
            "capacity_used": 0,
            "max_games": 100,
        }

    def test_status_reflects_active_rooms(self, client):
        client.post("/rooms", json={"room_id": "r1"})
        response = client.get("/status")
        data = response.json()
        assert data["active_rooms"] == 1
        assert data["active_games"] == 0
        assert data["capacity_used"] == 1


class TestCreateRoomEndpoint:
    @pytest.fixture
    def client(self):
        app = create_app(game_service=MockGameService())
        return TestClient(app)

    def test_create_room_success(self, client):
        response = client.post("/rooms", json={"room_id": "test-room"})
        assert response.status_code == 201
        assert response.json() == {"room_id": "test-room", "num_bots": 3, "status": "created"}

    def test_create_room_invalid_body(self, client):
        response = client.post("/rooms", content=b"not json")
        assert response.status_code == 400

    def test_create_room_invalid_room_id(self, client):
        response = client.post("/rooms", json={"room_id": "bad id!"})
        assert response.status_code == 400

    def test_create_room_duplicate(self, client):
        client.post("/rooms", json={"room_id": "dupe"})
        response = client.post("/rooms", json={"room_id": "dupe"})
        assert response.status_code == 409
        assert response.json() == {"error": "Room already exists"}

    def test_create_room_conflicts_with_existing_game(self, client):
        sm = client.app.state.session_manager
        sm._games["active-game"] = object()  # simulate an existing game
        response = client.post("/rooms", json={"room_id": "active-game"})
        assert response.status_code == 409
        assert response.json() == {"error": "Game with this ID already exists"}

    def test_create_room_with_custom_num_bots(self, client):
        response = client.post("/rooms", json={"room_id": "mixed-room", "num_bots": 2})
        assert response.status_code == 201
        assert response.json() == {"room_id": "mixed-room", "num_bots": 2, "status": "created"}

    def test_create_room_with_zero_bots(self, client):
        response = client.post("/rooms", json={"room_id": "pvp-room", "num_bots": 0})
        assert response.status_code == 201
        assert response.json() == {"room_id": "pvp-room", "num_bots": 0, "status": "created"}

    def test_create_room_invalid_num_bots(self, client):
        response = client.post("/rooms", json={"room_id": "bad-room", "num_bots": 5})
        assert response.status_code == 400

    def test_list_rooms_shows_room_info(self, client):
        client.post("/rooms", json={"room_id": "bot-room", "num_bots": 3})
        client.post("/rooms", json={"room_id": "mixed-room", "num_bots": 1})

        response = client.get("/rooms")
        assert response.status_code == 200
        rooms = {r["room_id"]: r for r in response.json()["rooms"]}
        assert rooms["bot-room"]["num_bots"] == 3
        assert rooms["bot-room"]["humans_needed"] == 1
        assert rooms["mixed-room"]["num_bots"] == 1
        assert rooms["mixed-room"]["humans_needed"] == 3

    def test_create_room_at_capacity(self, client):
        for i in range(100):
            resp = client.post("/rooms", json={"room_id": f"r{i}"})
            assert resp.status_code == 201
        response = client.post("/rooms", json={"room_id": "overflow"})
        assert response.status_code == 503
        assert response.json() == {"error": "Server at capacity"}
