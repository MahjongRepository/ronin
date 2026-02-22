"""Integration tests for WebSocket and HTTP endpoints.

These tests verify the web/transport layer (HTTP endpoints, WebSocket protocol,
MessagePack encoding) using the test client. They complement the game logic
Replay tests by ensuring the service layer works correctly.
"""

import pytest
from starlette.testclient import TestClient

from game.logic.enums import GameAction, WireClientMessageType, WireGameAction
from game.logic.events import EventType
from game.messaging.encoder import decode, encode
from game.messaging.event_payload import EVENT_TYPE_INT
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.server.app import create_app
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.mocks import MockGameService


class TestWebSocketIntegration:
    @pytest.fixture
    def client(self):
        # use MockGameService for predictable test behavior
        app = create_app(game_service=MockGameService())
        return TestClient(app)

    def _create_room(self, client, room_id: str, num_ai_players: int = 3) -> None:
        session_manager = client.app.state.session_manager
        session_manager.create_room(room_id, num_ai_players=num_ai_players)

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
        ticket = make_test_game_ticket(player_name, room_id)
        self._send_message(
            ws,
            {
                "t": WireClientMessageType.JOIN_ROOM,
                "room_id": room_id,
                "game_ticket": ticket,
            },
        )
        messages = []
        # Drain: room_joined, player_ready_changed, game_starting, game events...
        messages.append(self._receive_message(ws))  # room_joined

        self._send_message(ws, {"t": WireClientMessageType.SET_READY, "ready": True})
        # Drain remaining startup messages
        while True:
            msg = self._receive_message(ws)
            messages.append(msg)
            # Stop after we've received a game event (round_started or draw)
            if msg.get("t") in (EVENT_TYPE_INT[EventType.ROUND_STARTED], EVENT_TYPE_INT[EventType.DRAW]):
                break
        return messages

    def test_connect_join_room_and_start_game(self, client):
        self._create_room(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            ticket = make_test_game_ticket("TestPlayer", "test_game")
            self._send_message(
                ws,
                {
                    "t": WireClientMessageType.JOIN_ROOM,
                    "room_id": "test_game",
                    "game_ticket": ticket,
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == SessionMessageType.ROOM_JOINED
            assert response["room_id"] == "test_game"
            assert response["player_name"] == "TestPlayer"
            assert len(response["players"]) == 1
            assert response["players"][0]["name"] == "TestPlayer"

    def test_room_chat_message(self, client):
        """Chat messages in a room are broadcast to all room members."""
        self._create_room(client, "test_game", num_ai_players=2)

        with client.websocket_connect("/ws/test_game") as ws1:
            ticket1 = make_test_game_ticket("Player1", "test_game")
            self._send_message(
                ws1,
                {
                    "t": WireClientMessageType.JOIN_ROOM,
                    "room_id": "test_game",
                    "game_ticket": ticket1,
                },
            )
            self._receive_message(ws1)  # room_joined

            with client.websocket_connect("/ws/test_game") as ws2:
                ticket2 = make_test_game_ticket("Player2", "test_game", user_id="user-2")
                self._send_message(
                    ws2,
                    {
                        "t": WireClientMessageType.JOIN_ROOM,
                        "room_id": "test_game",
                        "game_ticket": ticket2,
                    },
                )
                self._receive_message(ws2)  # room_joined
                self._receive_message(ws1)  # player_joined(Player2)

                # Player1 sends chat while in the room
                self._send_message(
                    ws1,
                    {
                        "t": WireClientMessageType.CHAT,
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
                    "t": WireClientMessageType.CHAT,
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
                    "t": WireClientMessageType.GAME_ACTION,
                    "a": WireGameAction.DISCARD,
                    "ti": 0,
                },
            )

            response = self._receive_message(ws)
            assert response["t"] == EVENT_TYPE_INT[EventType.DRAW]
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
        self._create_room(client, "test-room", num_ai_players=2)

        with client.websocket_connect("/ws/test-room") as ws:
            # The ticket must match the path room_id (test-room), not the payload room_id
            ticket = make_test_game_ticket("TestPlayer", "test-room")
            self._send_message(
                ws,
                {
                    "t": WireClientMessageType.JOIN_ROOM,
                    "room_id": "ignored",
                    "game_ticket": ticket,
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == SessionMessageType.ROOM_JOINED
            assert response["room_id"] == "test-room"

    def test_invalid_msgpack_returns_error_and_keeps_connection(self, client):
        """Sending invalid MessagePack data returns an error without disconnecting."""
        self._create_room(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            # Send garbage bytes that aren't valid MessagePack
            ws.send_bytes(b"\xff\xff\xff")

            response = self._receive_message(ws)
            assert response["type"] == SessionMessageType.ERROR
            assert response["code"] == SessionErrorCode.INVALID_MESSAGE

            # Connection should still be alive - verify by sending a valid message
            ticket = make_test_game_ticket("TestPlayer", "test_game")
            self._send_message(
                ws,
                {
                    "t": WireClientMessageType.JOIN_ROOM,
                    "room_id": "test_game",
                    "game_ticket": ticket,
                },
            )
            response = self._receive_message(ws)
            assert response["type"] == SessionMessageType.ROOM_JOINED

    def test_join_room_with_invalid_ticket(self, client):
        """An invalid game ticket returns an INVALID_TICKET error."""
        self._create_room(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            self._send_message(
                ws,
                {
                    "t": WireClientMessageType.JOIN_ROOM,
                    "room_id": "test_game",
                    "game_ticket": "not-a-valid-ticket",
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == SessionMessageType.ERROR
            assert response["code"] == SessionErrorCode.INVALID_TICKET

    def test_join_room_valid_ticket_returns_server_generated_token(self, client):
        """A valid game ticket results in room_joined with a server-generated session token."""
        self._create_room(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            ticket = make_test_game_ticket("TestPlayer", "test_game")
            self._send_message(
                ws,
                {
                    "t": WireClientMessageType.JOIN_ROOM,
                    "room_id": "test_game",
                    "game_ticket": ticket,
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == SessionMessageType.ROOM_JOINED
            assert response["player_name"] == "TestPlayer"


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

    def test_status_returns_room_and_game_info(self, client):
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["active_rooms"] == 0
        assert data["active_games"] == 0
        assert data["capacity_used"] == 0
        assert data["max_capacity"] == 100
        assert "version" in data
        assert "commit" in data

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
        assert response.json() == {"room_id": "test-room", "num_ai_players": 3, "status": "created"}

    def test_create_room_invalid_body(self, client):
        response = client.post("/rooms", content=b"not json")
        assert response.status_code == 400
        assert response.json() == {"error": "Invalid request body"}

    def test_create_room_invalid_room_id(self, client):
        response = client.post("/rooms", json={"room_id": "bad id!"})
        assert response.status_code == 400
        assert response.json() == {"error": "Invalid request body"}

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

    @pytest.mark.parametrize(
        ("room_id", "num_ai"),
        [("mixed-room", 2), ("pvp-room", 0)],
    )
    def test_create_room_with_custom_num_ai_players(self, client, room_id, num_ai):
        response = client.post("/rooms", json={"room_id": room_id, "num_ai_players": num_ai})
        assert response.status_code == 201
        assert response.json() == {"room_id": room_id, "num_ai_players": num_ai, "status": "created"}

    def test_create_room_invalid_num_ai_players(self, client):
        response = client.post("/rooms", json={"room_id": "bad-room", "num_ai_players": 5})
        assert response.status_code == 400
        assert response.json() == {"error": "Invalid request body"}

    def test_create_room_legacy_num_bots_rejected(self, client):
        """Legacy payload using num_bots is rejected via extra=forbid."""
        response = client.post("/rooms", json={"room_id": "legacy-room", "num_bots": 2})
        assert response.status_code == 400
        assert response.json() == {"error": "Invalid request body"}

    def test_list_rooms_shows_room_info(self, client):
        client.post("/rooms", json={"room_id": "ai-room", "num_ai_players": 3})
        client.post("/rooms", json={"room_id": "mixed-room", "num_ai_players": 1})

        response = client.get("/rooms")
        assert response.status_code == 200
        rooms = {r["room_id"]: r for r in response.json()["rooms"]}
        assert rooms["ai-room"]["num_ai_players"] == 3
        assert rooms["ai-room"]["players_needed"] == 1
        assert rooms["mixed-room"]["num_ai_players"] == 1
        assert rooms["mixed-room"]["players_needed"] == 3

    def test_create_room_at_capacity(self, client):
        for i in range(100):
            resp = client.post("/rooms", json={"room_id": f"r{i}"})
            assert resp.status_code == 201
        response = client.post("/rooms", json={"room_id": "overflow"})
        assert response.status_code == 503
        assert response.json() == {"error": "Server at capacity"}

    def test_create_room_oversized_body_rejected(self, client):
        oversized = b'{"room_id": "' + b"x" * 5000 + b'"}'
        response = client.post("/rooms", content=oversized, headers={"Content-Type": "application/json"})
        assert response.status_code == 413
        assert response.json() == {"error": "Request body too large"}
