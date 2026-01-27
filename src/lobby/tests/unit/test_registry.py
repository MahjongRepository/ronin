from lobby.registry.types import GameServer


class TestGameServer:
    def test_create_server(self):
        server = GameServer(name="test", url="http://localhost:8001")
        assert server.name == "test"
        assert server.url == "http://localhost:8001"
        assert server.healthy is False
