import pytest
from starlette.testclient import TestClient

from game.server.app import create_app


class TestWebSocketIntegration:
    @pytest.fixture
    def client(self):
        app = create_app()
        return TestClient(app)

    def _create_room(self, client, room_id: str) -> dict:
        response = client.post("/rooms", json={"room_id": room_id})
        assert response.status_code == 201
        return response.json()

    def test_connect_and_join_room(self, client):
        self._create_room(client, "test_room")

        with client.websocket_connect("/ws/test_room") as ws:
            ws.send_json(
                {
                    "type": "join_room",
                    "room_id": "test_room",
                    "player_name": "TestPlayer",
                }
            )

            response = ws.receive_json()
            assert response["type"] == "room_joined"
            assert response["room_id"] == "test_room"
            assert "TestPlayer" in response["players"]

    def test_two_players_in_room(self, client):
        self._create_room(client, "test_room")

        with client.websocket_connect("/ws/test_room") as ws1:
            ws1.send_json(
                {
                    "type": "join_room",
                    "room_id": "test_room",
                    "player_name": "Player1",
                }
            )
            ws1.receive_json()  # room_joined

            with client.websocket_connect("/ws/test_room") as ws2:
                ws2.send_json(
                    {
                        "type": "join_room",
                        "room_id": "test_room",
                        "player_name": "Player2",
                    }
                )

                # Player2 receives room_joined
                response = ws2.receive_json()
                assert response["type"] == "room_joined"
                assert set(response["players"]) == {"Player1", "Player2"}

                # Player1 receives player_joined notification
                notification = ws1.receive_json()
                assert notification["type"] == "player_joined"
                assert notification["player_name"] == "Player2"

    def test_chat_message(self, client):
        self._create_room(client, "test_room")

        with client.websocket_connect("/ws/test_room") as ws1:
            ws1.send_json(
                {
                    "type": "join_room",
                    "room_id": "test_room",
                    "player_name": "Player1",
                }
            )
            ws1.receive_json()  # room_joined

            with client.websocket_connect("/ws/test_room") as ws2:
                ws2.send_json(
                    {
                        "type": "join_room",
                        "room_id": "test_room",
                        "player_name": "Player2",
                    }
                )
                ws2.receive_json()  # room_joined
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
        self._create_room(client, "test_room")

        with client.websocket_connect("/ws/test_room") as ws:
            ws.send_json(
                {
                    "type": "join_room",
                    "room_id": "test_room",
                    "player_name": "Player1",
                }
            )
            ws.receive_json()  # room_joined

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
        self._create_room(client, "test_room")

        with client.websocket_connect("/ws/test_room") as ws:
            ws.send_json({"type": "invalid"})

            response = ws.receive_json()
            assert response["type"] == "error"
            assert response["code"] == "invalid_message"
