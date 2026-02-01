from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from game.logic.mock import MockGameService
from game.messaging.encoder import decode, encode
from game.server.app import create_app
from game.server.websocket import WebSocketConnection


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
        self._create_game(client, "test_game", num_bots=2)

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
        self._create_game(client, "test_game", num_bots=2)

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

                # drain game_started and round_started events
                self._receive_message(ws1)  # game_started
                self._receive_message(ws1)  # round_started for seat_0
                self._receive_message(ws2)  # game_started

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
            self._receive_message(ws)  # game_started event (broadcast)
            self._receive_message(ws)  # round_started event for seat_0

            self._send_message(
                ws,
                {
                    "type": "game_action",
                    "action": "test_action",
                    "data": {"foo": "bar"},
                },
            )

            response = self._receive_message(ws)
            assert response["type"] == "test_action_result"
            assert response["player"] == "Player1"
            assert response["success"] is True

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
            assert game["num_bots"] == 3


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

    def test_create_game_negative_num_bots(self, client):
        response = client.post("/games", json={"game_id": "bad-game", "num_bots": -1})
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


class TestWebSocketConnection:
    async def test_close_delegates_to_underlying_websocket(self):
        mock_ws = MagicMock()
        mock_ws.close = AsyncMock()
        conn = WebSocketConnection(mock_ws, connection_id="test-conn")

        await conn.close(code=1001, reason="going away")

        mock_ws.close.assert_called_once_with(code=1001, reason="going away")

    async def test_send_bytes_converts_disconnect_to_connection_error(self):
        mock_ws = MagicMock()
        mock_ws.send_bytes = AsyncMock(side_effect=WebSocketDisconnect())
        conn = WebSocketConnection(mock_ws, connection_id="test-conn")

        with pytest.raises(ConnectionError, match="WebSocket already disconnected"):
            await conn.send_bytes(b"data")

    async def test_close_converts_disconnect_to_connection_error(self):
        mock_ws = MagicMock()
        mock_ws.close = AsyncMock(side_effect=WebSocketDisconnect())
        conn = WebSocketConnection(mock_ws, connection_id="test-conn")

        with pytest.raises(ConnectionError, match="WebSocket already disconnected"):
            await conn.close()


class TestStaticFiles:
    @pytest.fixture
    def client(self):
        app = create_app()
        return TestClient(app)

    def test_static_game_html_served(self, client):
        response = client.get("/static/game.legacy.html")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Ronin Game" in response.text
