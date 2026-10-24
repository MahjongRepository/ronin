import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Route

from lobby.auth.csrf import CSRF_COOKIE_NAME
from lobby.tests.conftest import make_player, open_client
from lobby.tests.integration.conftest import register_with_csrf
from shared.dal.models import PlayedGame, PlayedGameStanding

_GAME_CLIENT_INDEX = '<div id="app"></div><script type="module" src="/game-assets/assets/index-abc123.js"></script>'


def _create_lobby_assets(assets_dir):
    built_dir = assets_dir / "assets"
    built_dir.mkdir(parents=True)
    (built_dir / "lobby-test.js").write_text("console.log('lobby');")
    (built_dir / "lobby-test.css").write_text("body { color: red; }")

    vite_dir = assets_dir / ".vite"
    vite_dir.mkdir()
    (vite_dir / "manifest.json").write_text(
        json.dumps(
            {
                "src/index.ts": {
                    "file": "assets/lobby-test.js",
                    "css": ["assets/lobby-test.css"],
                    "isEntry": True,
                },
            },
        ),
    )


def _create_game_client_build(game_client_dir):
    built_dir = game_client_dir / "assets"
    built_dir.mkdir(parents=True)
    (built_dir / "index-abc123.js").write_text("console.log('game');")
    (game_client_dir / "index.html").write_text(_GAME_CLIENT_INDEX)


@pytest.fixture
def app(make_app, tmp_path, monkeypatch):
    monkeypatch.setattr("lobby.server.app.APP_VERSION", "dev")
    assets_dir = tmp_path / "lobby-dist"
    game_client_dir = tmp_path / "game-dist"
    _create_lobby_assets(assets_dir)
    _create_game_client_build(game_client_dir)
    return make_app(assets_dir=str(assets_dir), game_client_dir=str(game_client_dir))


class TestLobbyViews:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "viewuser")
        return client

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
        assert "/lobby-assets/assets/lobby-test.css" in response.text

    def test_lobby_page__when_visited__should_include_script_tag(self, client):
        response = client.get("/")
        assert "/lobby-assets/assets/lobby-test.js" in response.text
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
        room_manager.join_room(
            room_id="abc12345-long-id", player=make_player(connection_id="conn-1", user_id="user-1", username="Alice")
        )

        response = client.get("/")
        assert "abc12345" in response.text
        assert "1/4" in response.text
        assert "Join" in response.text

    def test_lobby_page__when_room_full__should_mark_it_full(self, client):
        room_manager = client.app.state.room_manager
        room_manager.create_room("full-room")
        for i in range(4):
            room_manager.join_room(
                room_id="full-room",
                player=make_player(connection_id=f"conn-full-{i}", user_id=f"user-full-{i}", username=f"Player{i}"),
            )

        response = client.get("/")
        assert "full-roo" in response.text
        assert "Full" in response.text

    def test_static_css_route__should_serve_stylesheet(self, client):
        response = client.get("/static/styles/lobby.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_play_page__when_visited__should_serve_game_client_index(self, client):
        response = client.get("/play/test-game")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert response.text == _GAME_CLIENT_INDEX

    @pytest.mark.parametrize(
        "page", ["board", "discards", "hand", "melds", "decisions", "table", "win", "draw", "standings"]
    )
    def test_storybook_page__when_visited__should_serve_game_client_index(self, client, page):
        response = client.get(f"/play/storybook/{page}")
        assert response.status_code == 200
        assert response.text == _GAME_CLIENT_INDEX

    def test_play_page__when_index_missing__should_return_503(self, make_app, tmp_path):
        game_client_dir = tmp_path / "empty-game-dist"
        game_client_dir.mkdir()

        app = make_app(game_client_dir=str(game_client_dir))
        with open_client(app) as c:
            register_with_csrf(c, "testuser")

            response = c.get("/play/test-game")
            assert response.status_code == 503
            assert "Game client assets not available" in response.text

    def test_game_assets_route__when_asset_requested__should_serve_it(self, client):
        response = client.get("/game-assets/assets/index-abc123.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        assert response.text == "console.log('game');"

    def test_game_assets_route__when_dir_missing__should_not_mount(self, make_app, tmp_path):
        app = make_app(game_client_dir=str(tmp_path / "no-such-dir"))
        route_names = {r.name for r in app.routes}
        assert "game_assets" not in route_names

    def test_lobby_assets_route__when_asset_requested__should_serve_it(self, client):
        response = client.get("/lobby-assets/assets/lobby-test.js")
        assert response.status_code == 200
        assert response.text == "console.log('lobby');"

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

    def test_room_page__when_first_visit__should_set_csrf_cookie(self, client):
        client.app.state.room_manager.create_room("fresh-room")
        client.cookies.delete(CSRF_COOKIE_NAME)

        response = client.get("/rooms/fresh-room")
        assert response.status_code == 200
        assert CSRF_COOKIE_NAME in response.cookies

    def test_room_page__when_room_not_found__should_redirect_to_lobby(self, client):
        response = client.get("/rooms/nonexistent-room", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    def test_storybook_page__when_first_visit__should_set_csrf_cookie(self, app):
        with open_client(app) as c:
            response = c.get("/storybook")
            assert response.status_code == 200
            assert CSRF_COOKIE_NAME in response.cookies

    def test_storybook_page__when_visited__should_return_html(self, client):
        response = client.get("/storybook")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Style Guide" in response.text
        assert "Typography" in response.text
        assert "Buttons" in response.text
        assert "Form Elements" in response.text


_DEV_GAME_CLIENT_PAGE = '<script type="module" src="/game-assets/@vite/client"></script>'


async def _dev_game_client_page(request):
    if "text/html" not in request.headers.get("accept", ""):
        return PlainTextResponse("not html", status_code=406)

    return HTMLResponse(_DEV_GAME_CLIENT_PAGE)


async def _dev_game_client_file(request):
    return PlainTextResponse(
        f"{request.path_params['path']}?{request.scope['query_string'].decode()}",
        media_type="text/javascript",
        headers={"etag": '"v1"', "x-dev-only": "1"},
    )


_DEV_GAME_CLIENT_SERVER = Starlette(
    routes=[
        Route("/game-assets/", _dev_game_client_page),
        Route("/game-assets/{path:path}", _dev_game_client_file),
    ],
)


def _refuse_connection(request):
    raise httpx.ConnectError("connection refused", request=request)


class TestViteDevMode:
    @pytest.fixture
    def app(self, make_app, monkeypatch):
        monkeypatch.setattr("lobby.server.app.APP_VERSION", "dev")
        return make_app(
            vite_dev_url="http://localhost:5173",
            game_client_dev_url="http://localhost:5174",
            game_client_dev_transport=httpx.ASGITransport(app=_DEV_GAME_CLIENT_SERVER),
        )

    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "viteuser")
        return client

    def test_lobby_page__when_vite_dev_url_set__should_use_vite_dev_urls(self, client):
        response = client.get("/")
        assert "http://localhost:5173/src/styles/lobby-app.scss" in response.text
        assert "http://localhost:5173/src/index.ts" in response.text
        assert "http://localhost:5173/@vite/client" in response.text

    def test_play_page__when_game_client_dev_url_set__should_serve_dev_server_page(self, client):
        response = client.get("/play/test-game")
        assert response.status_code == 200
        assert response.text == _DEV_GAME_CLIENT_PAGE

    def test_game_assets_route__when_game_client_dev_url_set__should_proxy_encoded_path_and_query(self, client):
        response = client.get("/game-assets/src/tile%23back.svg?import&t=1")
        assert response.status_code == 200
        assert response.text == "src/tile#back.svg?import&t=1"
        assert "javascript" in response.headers["content-type"]
        assert response.headers["etag"] == '"v1"'
        assert "x-dev-only" not in response.headers

    def test_game_assets_route__when_dev_server_unreachable__should_return_502(self, make_app):
        app = make_app(
            game_client_dev_url="http://localhost:5174",
            game_client_dev_transport=httpx.MockTransport(_refuse_connection),
        )
        with open_client(app) as c:
            response = c.get("/game-assets/src/index.ts")
            assert response.status_code == 502


class TestHistoryPage:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "gamesuser")
        return client

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
        client.app.state.game_repo.create_game(game)

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
            client.app.state.game_repo.create_game(game)

        response = client.get("/history")
        assert response.status_code == 200
        assert "completed-game" in response.text
        assert "active-game" not in response.text
        assert "abandoned-game" not in response.text

    def test_history_page__when_unauthenticated__should_redirect_to_login(self, app):
        with open_client(app) as c:
            response = c.get("/history", follow_redirects=False)
            assert response.status_code == 303
            assert "/login" in response.headers["location"]
