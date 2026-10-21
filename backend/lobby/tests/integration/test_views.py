import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from lobby.auth.csrf import CSRF_COOKIE_NAME
from lobby.server.app import create_app
from lobby.settings import LobbyServerSettings
from lobby.tests.integration.conftest import register_with_csrf
from shared.auth.settings import AuthSettings
from shared.dal.models import PlayedGame, PlayedGameStanding


def _create_vite_manifest(game_assets_dir):
    assets_dir = game_assets_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "game-abc123.js").write_text("console.log('game');")
    (assets_dir / "game-abc123.css").write_text("body{}")
    (assets_dir / "lobby-test.js").write_text("console.log('lobby');")
    (assets_dir / "lobby-test.css").write_text("body { color: red; }")

    vite_dir = game_assets_dir / ".vite"
    vite_dir.mkdir()
    (vite_dir / "manifest.json").write_text(
        json.dumps(
            {
                "src/index.ts": {
                    "file": "assets/game-abc123.js",
                    "css": ["assets/game-abc123.css"],
                    "isEntry": True,
                },
                "src/lobby/index.ts": {
                    "file": "assets/lobby-test.js",
                    "css": ["assets/lobby-test.css"],
                    "isEntry": True,
                },
            },
        ),
    )


class TestLobbyViews:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setattr("lobby.server.app.APP_VERSION", "dev")
        config_file = tmp_path / "servers.yaml"
        servers_yaml = """
servers:
  - name: "test-server"
    url: "http://localhost:8711"
"""
        config_file.write_text(servers_yaml)
        static_dir = tmp_path / "public"
        (static_dir / "styles").mkdir(parents=True)
        (static_dir / "styles" / "lobby.css").write_text("body { color: red; }")

        game_assets_dir = tmp_path / "dist"
        game_assets_dir.mkdir()
        _create_vite_manifest(game_assets_dir)

        app = create_app(
            settings=LobbyServerSettings(
                config_path=config_file,
                static_dir=str(static_dir),
                game_assets_dir=str(game_assets_dir),
            ),
            auth_settings=AuthSettings(
                game_ticket_secret="test-secret",
                database_path=str(tmp_path / "test.db"),
                cookie_secure=False,
            ),
        )
        c = TestClient(app)
        # Register and login a user for authenticated view tests
        register_with_csrf(c, "viewuser")
        yield c
        app.state.db.close()

    def test_lobby_page__when_first_visit__should_set_csrf_cookie(self, client):
        client.cookies.delete(CSRF_COOKIE_NAME)
        response = client.get("/")
        assert response.status_code == 200
        assert CSRF_COOKIE_NAME in response.cookies

    def test_lobby_page__when_visited__should_return_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Ronin" in response.text

    def test_lobby_page__when_visited__should_include_css_link(self, client):
        response = client.get("/")
        assert "/game-assets/assets/lobby-test.css" in response.text

    def test_lobby_page__when_visited__should_include_script_tag(self, client):
        response = client.get("/")
        assert "/game-assets/assets/lobby-test.js" in response.text
        assert '<script type="module"' in response.text

    def test_lobby_page__when_visited__should_show_create_room_form(self, client):
        response = client.get("/")
        assert 'action="/rooms/new"' in response.text

    def test_lobby_page__when_no_rooms__should_show_empty_message(self, client):
        response = client.get("/")
        assert "No tables yet" in response.text

    def test_lobby_page__when_room_has_player__should_list_it_with_join(self, client):
        room_manager = client.app.state.room_manager
        room_manager.create_room("abc12345-long-id")
        room_manager.join_room("conn-1", "abc12345-long-id", "user-1", "Alice")

        response = client.get("/")
        assert "abc12345" in response.text
        assert "1/4" in response.text
        assert "Join" in response.text

    def test_lobby_page__when_room_full__should_mark_it_full(self, client):
        room_manager = client.app.state.room_manager
        room_manager.create_room("full-room")
        for i in range(4):
            room_manager.join_room(f"conn-full-{i}", "full-room", f"user-full-{i}", f"Player{i}")

        response = client.get("/")
        assert "full-roo" in response.text
        assert "Full" in response.text

    def test_static_css_route__should_serve_stylesheet(self, client):
        response = client.get("/static/styles/lobby.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_play_page__when_visited__should_return_html(self, client):
        response = client.get("/play/test-game")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_play_page__when_visited__should_include_hashed_script(self, client):
        response = client.get("/play/test-game")
        assert "/game-assets/assets/game-abc123.js" in response.text

    def test_play_page__when_visited__should_include_hashed_css(self, client):
        response = client.get("/play/test-game")
        assert "/game-assets/assets/game-abc123.css" in response.text

    def test_storybook_melds_page__when_visited__should_return_html(self, client):
        response = client.get("/play/storybook/melds")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_storybook_hand_page__when_visited__should_return_html(self, client):
        response = client.get("/play/storybook/hand")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_storybook_discards_page__when_visited__should_return_html(self, client):
        response = client.get("/play/storybook/discards")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_play_page__when_assets_missing__should_return_503(self, tmp_path):
        config_file = tmp_path / "servers.yaml"
        config_file.write_text("servers:\n  - name: test\n    url: http://localhost:8711\n")
        static_dir = tmp_path / "public"
        (static_dir / "styles").mkdir(parents=True)
        (static_dir / "styles" / "lobby.css").write_text("")
        game_assets_dir = tmp_path / "dist"
        game_assets_dir.mkdir()
        vite_dir = game_assets_dir / ".vite"
        vite_dir.mkdir()
        (vite_dir / "manifest.json").write_text("{}")
        app = create_app(
            settings=LobbyServerSettings(
                config_path=config_file,
                static_dir=str(static_dir),
                game_assets_dir=str(game_assets_dir),
            ),
            auth_settings=AuthSettings(
                game_ticket_secret="s",
                database_path=str(tmp_path / "test.db"),
                cookie_secure=False,
            ),
        )
        c = TestClient(app)
        register_with_csrf(c, "testuser")
        response = c.get("/play/test-game")
        assert response.status_code == 503
        assert "Game client assets not available" in response.text
        app.state.db.close()

    def test_game_assets_route__when_asset_requested__should_serve_it(self, client):
        response = client.get("/game-assets/assets/game-abc123.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        assert "console.log('game')" in response.text

    def test_game_assets_route__when_dir_missing__should_not_mount(self, tmp_path):
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
                cookie_secure=False,
            ),
        )
        route_names = {r.name for r in app.routes}
        assert "game_assets" not in route_names
        app.state.db.close()

    def test_matchmaking_page__when_visited__should_return_html(self, client):
        response = client.get("/matchmaking")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "matchmaking-app" in response.text
        assert "ws://" in response.text

    def test_matchmaking_page__when_first_visit__should_set_csrf_cookie(self, client):
        client.cookies.delete(CSRF_COOKIE_NAME)
        response = client.get("/matchmaking")
        assert response.status_code == 200
        assert CSRF_COOKIE_NAME in response.cookies

    def test_room_page__when_room_exists__should_render_room_template(self, client):
        room_manager = client.app.state.room_manager
        room_manager.create_room("test-room-42")

        response = client.get("/rooms/test-room-42")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert 'data-room-id="test-room-42"' in response.text

    def test_room_page__when_first_visit__should_set_csrf_cookie(self, tmp_path, monkeypatch):
        monkeypatch.setattr("lobby.server.app.APP_VERSION", "dev")
        config_file = tmp_path / "cfg.yaml"
        config_file.write_text("servers:\n  - name: t\n    url: http://localhost:8711\n")
        static_dir = tmp_path / "pub"
        (static_dir / "styles").mkdir(parents=True)
        (static_dir / "styles" / "lobby.css").write_text("")
        app = create_app(
            settings=LobbyServerSettings(config_path=config_file, static_dir=str(static_dir)),
            auth_settings=AuthSettings(
                game_ticket_secret="s",
                database_path=str(tmp_path / "t.db"),
                cookie_secure=False,
            ),
        )
        c = TestClient(app)
        register_with_csrf(c, "roomuser")
        app.state.room_manager.create_room("fresh-room")
        # Clear the CSRF cookie to simulate a direct visit
        c.cookies.delete(CSRF_COOKIE_NAME)
        response = c.get("/rooms/fresh-room")
        assert response.status_code == 200
        assert CSRF_COOKIE_NAME in response.cookies
        app.state.db.close()

    def test_room_page__when_room_not_found__should_redirect_to_lobby(self, client):
        response = client.get("/rooms/nonexistent-room", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    def test_storybook_page__when_first_visit__should_set_csrf_cookie(self, tmp_path, monkeypatch):
        monkeypatch.setattr("lobby.server.app.APP_VERSION", "dev")
        config_file = tmp_path / "cfg.yaml"
        config_file.write_text("servers:\n  - name: t\n    url: http://localhost:8711\n")
        static_dir = tmp_path / "pub"
        (static_dir / "styles").mkdir(parents=True)
        (static_dir / "styles" / "lobby.css").write_text("")
        app = create_app(
            settings=LobbyServerSettings(config_path=config_file, static_dir=str(static_dir)),
            auth_settings=AuthSettings(
                game_ticket_secret="s",
                database_path=str(tmp_path / "t.db"),
                cookie_secure=False,
            ),
        )
        c = TestClient(app)
        # Don't register - visit storybook directly (no prior CSRF cookie)
        response = c.get("/storybook")
        assert response.status_code == 200
        assert CSRF_COOKIE_NAME in response.cookies
        app.state.db.close()

    def test_storybook_page__when_visited__should_return_html(self, client):
        response = client.get("/storybook")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Style Guide" in response.text
        assert "Typography" in response.text
        assert "Buttons" in response.text
        assert "Form Elements" in response.text


class TestViteDevMode:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setattr("lobby.server.app.APP_VERSION", "dev")
        config_file = tmp_path / "servers.yaml"
        config_file.write_text("servers:\n  - name: t\n    url: http://localhost:8711\n")
        static_dir = tmp_path / "pub"
        static_dir.mkdir()

        app = create_app(
            settings=LobbyServerSettings(
                config_path=config_file,
                static_dir=str(static_dir),
                vite_dev_url="http://localhost:5173",
            ),
            auth_settings=AuthSettings(
                game_ticket_secret="s",
                database_path=str(tmp_path / "t.db"),
                cookie_secure=False,
            ),
        )
        c = TestClient(app)
        register_with_csrf(c, "viteuser")
        yield c
        app.state.db.close()

    def test_lobby_page__when_vite_dev_url_set__should_use_vite_dev_urls(self, client):
        response = client.get("/")
        assert "http://localhost:5173/src/styles/lobby-app.scss" in response.text
        assert "http://localhost:5173/src/lobby/index.ts" in response.text
        assert "http://localhost:5173/@vite/client" in response.text

    def test_play_page__when_vite_dev_url_set__should_use_vite_dev_urls(self, client):
        response = client.get("/play/test-game")
        assert response.status_code == 200
        assert "http://localhost:5173/src/styles/game-app.scss" in response.text
        assert "http://localhost:5173/src/index.ts" in response.text
        assert "http://localhost:5173/@vite/client" in response.text


class TestHistoryPage:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setattr("lobby.server.app.APP_VERSION", "dev")
        config_file = tmp_path / "servers.yaml"
        config_file.write_text("servers:\n  - name: test\n    url: http://localhost:8711\n")
        static_dir = tmp_path / "public"
        (static_dir / "styles").mkdir(parents=True)
        (static_dir / "styles" / "lobby.css").write_text("")
        game_assets_dir = tmp_path / "dist"
        game_assets_dir.mkdir()
        _create_vite_manifest(game_assets_dir)
        app = create_app(
            settings=LobbyServerSettings(
                config_path=config_file,
                static_dir=str(static_dir),
                game_assets_dir=str(game_assets_dir),
            ),
            auth_settings=AuthSettings(
                game_ticket_secret="test-secret",
                database_path=str(tmp_path / "test.db"),
                cookie_secure=False,
            ),
        )
        c = TestClient(app)
        register_with_csrf(c, "gamesuser")
        yield c
        app.state.db.close()

    def test_history_page__when_first_visit__should_set_csrf_cookie(self, client):
        client.cookies.delete(CSRF_COOKIE_NAME)
        response = client.get("/history")
        assert response.status_code == 200
        assert CSRF_COOKIE_NAME in response.cookies

    def test_history_page__when_no_games__should_show_empty_state(self, client):
        response = client.get("/history")
        assert response.status_code == 200
        assert "No games played yet" in response.text

    def test_history_page__when_game_completed__should_show_standings(self, client):
        now = datetime.now(UTC)
        game = PlayedGame(
            game_id="abcd1234-test-game",
            started_at=now - timedelta(minutes=45),
            ended_at=now,
            end_reason="completed",
            game_type="hanchan",
            num_rounds_played=8,
            standings=[
                PlayedGameStanding(name="Winner", seat=0, score=40000, final_score=50),
                PlayedGameStanding(name="Second", seat=1, score=25000, final_score=0),
                PlayedGameStanding(name="Third", seat=2, score=20000, final_score=-15),
                PlayedGameStanding(name="Fourth", seat=3, score=15000, final_score=-35),
            ],
        )
        asyncio.run(client.app.state.game_repo.create_game(game))

        response = client.get("/history")
        assert response.status_code == 200
        assert "abcd1234" in response.text
        assert "Winner" in response.text
        assert "Second" in response.text
        assert "南" in response.text
        assert "games-standing--winner" in response.text
        assert "40000" in response.text
        assert "25000" in response.text

    def test_history_page__when_games_not_completed__should_hide_them(self, client):
        now = datetime.now(UTC)
        completed = PlayedGame(
            game_id="completed-game",
            started_at=now - timedelta(minutes=30),
            ended_at=now,
            end_reason="completed",
            game_type="hanchan",
            standings=[
                PlayedGameStanding(name="Alice", seat=0, score=40000, final_score=50),
            ],
        )
        active = PlayedGame(
            game_id="active-game",
            started_at=now,
            standings=[
                PlayedGameStanding(name="Bob", seat=0),
            ],
        )
        abandoned = PlayedGame(
            game_id="abandoned-game",
            started_at=now - timedelta(minutes=5),
            ended_at=now,
            end_reason="abandoned",
            standings=[
                PlayedGameStanding(name="Charlie", seat=0),
            ],
        )
        for game in (completed, active, abandoned):
            asyncio.run(client.app.state.game_repo.create_game(game))

        response = client.get("/history")
        assert response.status_code == 200
        assert "completed-game" in response.text
        assert "active-game" not in response.text
        assert "abandoned-game" not in response.text

    def test_history_page__when_unauthenticated__should_redirect_to_login(self, tmp_path, monkeypatch):
        monkeypatch.setattr("lobby.server.app.APP_VERSION", "dev")
        config_file = tmp_path / "cfg.yaml"
        config_file.write_text("servers:\n  - name: t\n    url: http://localhost:8711\n")
        static_dir = tmp_path / "pub"
        (static_dir / "styles").mkdir(parents=True)
        (static_dir / "styles" / "lobby.css").write_text("")
        app = create_app(
            settings=LobbyServerSettings(config_path=config_file, static_dir=str(static_dir)),
            auth_settings=AuthSettings(
                game_ticket_secret="s",
                database_path=str(tmp_path / "t.db"),
                cookie_secure=False,
            ),
        )
        c = TestClient(app)
        response = c.get("/history", follow_redirects=False)
        assert response.status_code == 303
        assert "/login" in response.headers["location"]
        app.state.db.close()
