import pytest
from starlette.testclient import TestClient

from game.logic.mock import MockGameService
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

    def test_connect_and_join_game(self, client):
        self._create_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            ws.send_json(
                {
                    "type": "join_game",
                    "game_id": "test_game",
                    "player_name": "TestPlayer",
                }
            )

            response = ws.receive_json()
            assert response["type"] == "game_joined"
            assert response["game_id"] == "test_game"
            assert response["players"] == ["TestPlayer"]

    def test_two_players_in_game(self, client):
        self._create_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws1:
            ws1.send_json(
                {
                    "type": "join_game",
                    "game_id": "test_game",
                    "player_name": "Player1",
                }
            )
            ws1.receive_json()  # game_joined
            ws1.receive_json()  # game_started event for seat_0

            with client.websocket_connect("/ws/test_game") as ws2:
                ws2.send_json(
                    {
                        "type": "join_game",
                        "game_id": "test_game",
                        "player_name": "Player2",
                    }
                )

                # Player2 receives game_joined
                response = ws2.receive_json()
                assert response["type"] == "game_joined"
                assert set(response["players"]) == {"Player1", "Player2"}

                # Player1 receives player_joined notification
                notification = ws1.receive_json()
                assert notification["type"] == "player_joined"
                assert notification["player_name"] == "Player2"

    def test_chat_message(self, client):
        self._create_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws1:
            ws1.send_json(
                {
                    "type": "join_game",
                    "game_id": "test_game",
                    "player_name": "Player1",
                }
            )
            ws1.receive_json()  # game_joined
            ws1.receive_json()  # game_started event for seat_0

            with client.websocket_connect("/ws/test_game") as ws2:
                ws2.send_json(
                    {
                        "type": "join_game",
                        "game_id": "test_game",
                        "player_name": "Player2",
                    }
                )
                ws2.receive_json()  # game_joined
                ws1.receive_json()  # player_joined

                # Player1 sends chat
                ws1.send_json(
                    {
                        "type": "chat",
                        "text": "Hello!",
                    }
                )

                # Both players receive the chat
                chat1 = ws1.receive_json()
                chat2 = ws2.receive_json()

                assert chat1["type"] == "chat"
                assert chat1["player_name"] == "Player1"
                assert chat1["text"] == "Hello!"
                assert chat2 == chat1

    def test_game_action(self, client):
        self._create_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            ws.send_json(
                {
                    "type": "join_game",
                    "game_id": "test_game",
                    "player_name": "Player1",
                }
            )
            ws.receive_json()  # game_joined
            ws.receive_json()  # game_started event for seat_0

            ws.send_json(
                {
                    "type": "game_action",
                    "action": "test_action",
                    "data": {"foo": "bar"},
                }
            )

            response = ws.receive_json()
            assert response["type"] == "game_event"
            assert response["event"] == "test_action_result"
            assert response["data"]["player"] == "Player1"
            assert response["data"]["success"] is True

    def test_invalid_message(self, client):
        self._create_game(client, "test_game")

        with client.websocket_connect("/ws/test_game") as ws:
            ws.send_json({"type": "invalid"})

            response = ws.receive_json()
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
