"""Integration tests for lobby HTML views with local room management."""

import json

import pytest
from starlette.testclient import TestClient

from lobby.server.app import create_app
from lobby.server.settings import LobbyServerSettings
from shared.auth.settings import AuthSettings


class TestLobbyViews:
    @pytest.fixture
    def client(self, tmp_path):
        config_file = tmp_path / "servers.yaml"
        config_file.write_text("""
servers:
  - name: "test-server"
    url: "http://localhost:8711"
""")
        static_dir = tmp_path / "public"
        (static_dir / "styles").mkdir(parents=True)
        (static_dir / "styles" / "lobby.css").write_text("body { color: red; }")

        game_assets_dir = tmp_path / "dist"
        game_assets_dir.mkdir()
        (game_assets_dir / "index-abc123.js").write_text("console.log('game');")
        (game_assets_dir / "index-abc123.css").write_text("body{}")
        (game_assets_dir / "lobby-test.css").write_text("body { color: red; }")
        (game_assets_dir / "manifest.json").write_text(
            json.dumps({"js": "index-abc123.js", "css": "index-abc123.css", "lobby_css": "lobby-test.css"}),
        )

        app = create_app(
            settings=LobbyServerSettings(
                config_path=config_file,
                static_dir=str(static_dir),
                game_assets_dir=str(game_assets_dir),
            ),
            auth_settings=AuthSettings(
                game_ticket_secret="test-secret",
                database_path=str(tmp_path / "test.db"),
            ),
        )
        c = TestClient(app)
        # Register and login a user for authenticated view tests
        c.post(
            "/register",
            data={"username": "viewuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        yield c
        app.state.db.close()

    def test_lobby_page_returns_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Ronin Mahjong" in response.text

    def test_lobby_page_includes_css_link(self, client):
        response = client.get("/")
        assert "/game-assets/lobby-test.css" in response.text

    def test_lobby_page_has_no_script_tags(self, client):
        response = client.get("/")
        assert "<script" not in response.text

    def test_lobby_page_shows_create_room_form(self, client):
        response = client.get("/")
        assert '<form method="POST" action="/rooms/new">' in response.text

    def test_lobby_page_shows_empty_message(self, client):
        response = client.get("/")
        assert "No rooms available. Create one!" in response.text

    def test_lobby_page_shows_rooms(self, client):
        room_manager = client.app.state.room_manager
        room_manager.create_room("abc123", num_ai_players=2)
        room_manager.join_room("conn-1", "abc123", "user-1", "Alice")

        response = client.get("/")
        assert "abc123" in response.text
        assert "1/2 players" in response.text
        assert "Join" in response.text

    def test_lobby_page_shows_full_room(self, client):
        room_manager = client.app.state.room_manager
        room_manager.create_room("full-room", num_ai_players=2)
        room_manager.join_room("conn-full-1", "full-room", "user-full-1", "Player1")
        room_manager.join_room("conn-full-2", "full-room", "user-full-2", "Player2")

        response = client.get("/")
        assert "full-room" in response.text
        assert "Full" in response.text

    def test_static_css_served(self, client):
        response = client.get("/static/styles/lobby.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_game_page_returns_html(self, client):
        response = client.get("/game")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_game_page_includes_hashed_script(self, client):
        response = client.get("/game")
        assert "/game-assets/index-abc123.js" in response.text

    def test_game_page_includes_hashed_css(self, client):
        response = client.get("/game")
        assert "/game-assets/index-abc123.css" in response.text

    def test_game_page_returns_503_when_assets_missing(self, tmp_path):
        """Authenticated request to /game returns 503 when manifest is empty."""
        config_file = tmp_path / "servers.yaml"
        config_file.write_text("servers:\n  - name: test\n    url: http://localhost:8711\n")
        static_dir = tmp_path / "public"
        (static_dir / "styles").mkdir(parents=True)
        (static_dir / "styles" / "lobby.css").write_text("")
        game_assets_dir = tmp_path / "dist"
        game_assets_dir.mkdir()
        (game_assets_dir / "manifest.json").write_text("{}")
        app = create_app(
            settings=LobbyServerSettings(
                config_path=config_file,
                static_dir=str(static_dir),
                game_assets_dir=str(game_assets_dir),
            ),
            auth_settings=AuthSettings(
                game_ticket_secret="s",
                database_path=str(tmp_path / "test.db"),
            ),
        )
        c = TestClient(app)
        c.post(
            "/register",
            data={"username": "testuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        response = c.get("/game")
        assert response.status_code == 503
        assert "Game client assets not available" in response.text
        app.state.db.close()

    def test_game_assets_served(self, client):
        response = client.get("/game-assets/index-abc123.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        assert "console.log('game')" in response.text

    def test_game_assets_mount_skipped_when_dir_missing(self, tmp_path):
        """When game_assets_dir does not exist, /game-assets/ is not mounted."""
        config_file = tmp_path / "servers.yaml"
        config_file.write_text("servers:\n  - name: test\n    url: http://localhost:8711\n")
        static_dir = tmp_path / "public"
        (static_dir / "styles").mkdir(parents=True)
        (static_dir / "styles" / "lobby.css").write_text("")
        nonexistent_dir = tmp_path / "no-such-dir"
        app = create_app(
            settings=LobbyServerSettings(
                config_path=config_file,
                static_dir=str(static_dir),
                game_assets_dir=str(nonexistent_dir),
            ),
            auth_settings=AuthSettings(
                game_ticket_secret="s",
                database_path=str(tmp_path / "test.db"),
            ),
        )
        route_names = {r.name for r in app.routes}
        assert "game_assets" not in route_names
        app.state.db.close()

    def test_room_page_returns_template(self, client):
        """GET /rooms/{room_id} returns room page template when room exists."""
        room_manager = client.app.state.room_manager
        room_manager.create_room("test-room-42", num_ai_players=3)

        response = client.get("/rooms/test-room-42")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert 'data-room-id="test-room-42"' in response.text

    def test_room_page_redirects_when_room_not_found(self, client):
        """GET /rooms/{room_id} redirects to lobby if room does not exist."""
        response = client.get("/rooms/nonexistent-room", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"
