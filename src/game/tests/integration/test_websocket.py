import pytest
from starlette.testclient import TestClient

from game.logic.mock import MockGameService
from game.messaging.encoder import decode, encode
from game.server.app import create_app


class TestWebSocketIntegration:
    @pytest.fixture
    def client(self):
        # use MockGameService for predictable test behavior
        app = create_app(game_service=MockGameService())
        return TestClient(app)

    def _create_game(self, client, game_id: str) -> dict:
        response = client.post("/games", json={"game_id": game_id})
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
                    "type": "join_game",
                    "game_id": "test_game",
                    "player_name": "TestPlayer",
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == "game_joined"
            assert response["game_id"] == "test_game"
            assert response["players"] == ["TestPlayer"]

    def test_two_players_in_game(self, client):
        self._create_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws1:
            self._send_message(
                ws1,
                {
                    "type": "join_game",
                    "game_id": "test_game",
                    "player_name": "Player1",
                },
            )
            self._receive_message(ws1)  # game_joined
            self._receive_message(ws1)  # game_started event for seat_0

            with client.websocket_connect("/ws/test_game") as ws2:
                self._send_message(
                    ws2,
                    {
                        "type": "join_game",
                        "game_id": "test_game",
                        "player_name": "Player2",
                    },
                )

                # Player2 receives game_joined
                response = self._receive_message(ws2)
                assert response["type"] == "game_joined"
                assert set(response["players"]) == {"Player1", "Player2"}

                # Player1 receives player_joined notification
                notification = self._receive_message(ws1)
                assert notification["type"] == "player_joined"
                assert notification["player_name"] == "Player2"

    def test_chat_message(self, client):
        self._create_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws1:
            self._send_message(
                ws1,
                {
                    "type": "join_game",
                    "game_id": "test_game",
                    "player_name": "Player1",
                },
            )
            self._receive_message(ws1)  # game_joined
            self._receive_message(ws1)  # game_started event for seat_0

            with client.websocket_connect("/ws/test_game") as ws2:
                self._send_message(
                    ws2,
                    {
                        "type": "join_game",
                        "game_id": "test_game",
                        "player_name": "Player2",
                    },
                )
                self._receive_message(ws2)  # game_joined
                self._receive_message(ws1)  # player_joined

                # Player1 sends chat
                self._send_message(
                    ws1,
                    {
                        "type": "chat",
                        "text": "Hello!",
                    },
                )

                # Both players receive the chat
                chat1 = self._receive_message(ws1)
                chat2 = self._receive_message(ws2)

                assert chat1["type"] == "chat"
                assert chat1["player_name"] == "Player1"
                assert chat1["text"] == "Hello!"
                assert chat2 == chat1

    def test_game_action(self, client):
        self._create_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            self._send_message(
                ws,
                {
                    "type": "join_game",
                    "game_id": "test_game",
                    "player_name": "Player1",
                },
            )
            self._receive_message(ws)  # game_joined
            self._receive_message(ws)  # game_started event for seat_0

            self._send_message(
                ws,
                {
                    "type": "game_action",
                    "action": "test_action",
                    "data": {"foo": "bar"},
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == "game_event"
            assert response["event"] == "test_action_result"
            assert response["data"]["player"] == "Player1"
            assert response["data"]["success"] is True

    def test_invalid_message(self, client):
        self._create_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            self._send_message(ws, {"type": "invalid"})

            response = self._receive_message(ws)
            assert response["type"] == "error"
            assert response["code"] == "invalid_message"

    def test_list_games_empty(self, client):
        response = client.get("/games")
        assert response.status_code == 200
        data = response.json()
        assert data == {"games": []}

    def test_list_games_with_games(self, client):
        self._create_game(client, "game1")
        self._create_game(client, "game2")

        response = client.get("/games")
        assert response.status_code == 200
        data = response.json()
        assert len(data["games"]) == 2
        game_ids = {g["game_id"] for g in data["games"]}
        assert game_ids == {"game1", "game2"}
        for game in data["games"]:
            assert game["player_count"] == 0
            assert game["max_players"] == 4


class TestStaticFiles:
    @pytest.fixture
    def client(self):
        app = create_app()
        return TestClient(app)

    def test_static_game_html_served(self, client):
        response = client.get("/static/game.html")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Ronin Game" in response.text
