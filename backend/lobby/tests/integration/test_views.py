import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Route

from lobby.auth.csrf import CSRF_COOKIE_NAME
from lobby.tests.conftest import open_client
from lobby.tests.integration.conftest import register_with_csrf, session_user_id
from shared.dal.models import GameEndReason, PlayedGame, PlayedGameStanding

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.testclient import TestClient

_GAME_CLIENT_INDEX = '<div id="app"></div><script type="module" src="/game-assets/v2/assets/index-v2.js"></script>'


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


def _create_game_client_build(game_client_dir, *, index, script_name, script):
    built_dir = game_client_dir / "assets"
    built_dir.mkdir(parents=True)
    (built_dir / script_name).write_text(script)
    (game_client_dir / "index.html").write_text(index)


@pytest.fixture
def app(make_app, tmp_path, monkeypatch):
    monkeypatch.setattr("lobby.server.app.APP_VERSION", "dev")
    assets_dir = tmp_path / "lobby-dist"
    game_client_v2_dir = tmp_path / "game-v2-dist"
    _create_lobby_assets(assets_dir)
    _create_game_client_build(
        game_client_v2_dir, index=_GAME_CLIENT_INDEX, script_name="index-v2.js", script="console.log('game v2');"
    )
    return make_app(
        assets_dir=str(assets_dir),
        game_client_v2_dir=str(game_client_v2_dir),
    )


_SPA_SHELL_ROUTES = [
    *((path, HTTPStatus.SEE_OTHER) for path in ["/", "/rooms/any-room", "/matchmaking", "/history"]),
    *((path, HTTPStatus.OK) for path in ["/login", "/register"]),
]


@pytest.mark.parametrize(("path", "signed_out_status"), _SPA_SHELL_ROUTES)
def test_spa_shell_route__when_requested__should_answer_the_shell_and_send_signed_out_users_of_protected_ones_to_login(
    client: TestClient,
    path: str,
    signed_out_status: HTTPStatus,
):
    signed_out = client.get(path, params={"notice": "x"}, follow_redirects=False)
    assert signed_out.status_code == signed_out_status
    if signed_out_status == HTTPStatus.SEE_OTHER:
        assert signed_out.headers["location"] == f"/login?{urlencode({'next': f'{path}?notice=x'})}"

    register_with_csrf(client, "shelluser")
    client.cookies.delete(CSRF_COOKIE_NAME)
    client.cookies.set("lang", "ja")
    response = client.get(path)
    assert response.status_code == 200
    assert '<html lang="ja"' in response.text
    assert '<main class="container" id="lobby-spa">' in response.text
    assert f'<meta name="csrf-token" content="{response.cookies[CSRF_COOKIE_NAME]}">' in response.text
    assert '<meta name="ronin-app-version" content="dev">' in response.text
    assert '<meta name="ronin-release-url" content="">' in response.text
    assert f'<meta name="ronin-current-year" content="{datetime.now(tz=UTC).year}">' in response.text
    assert '<meta name="ronin-dev-mode" content="true">' in response.text
    assert '<link rel="stylesheet" href="/lobby-assets/assets/lobby-test.css">' in response.text
    assert '<script type="module" src="/lobby-assets/assets/lobby-test.js"></script>' in response.text
    assert "lobby-nav-link" not in response.text


class TestLobbyViews:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "viewuser")
        return client

    def test_static_css_route__should_serve_stylesheet(self, client):
        response = client.get("/static/styles/lobby.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    @pytest.mark.parametrize("path", ["/play/test-game", "/play/history/test-game", "/play/storybook"])
    @pytest.mark.parametrize("query", ["", "?debug"])
    def test_play_page__when_visited__should_serve_game_client_index(self, client, path, query):
        response = client.get(f"{path}{query}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert response.text == _GAME_CLIENT_INDEX

    @pytest.mark.parametrize("page", ["board", "discards", "hand", "melds", "rotate", "decisions", "replay", "sounds"])
    def test_storybook_page__when_visited__should_serve_game_client_index(self, client, page):
        response = client.get(f"/play/storybook/{page}")
        assert response.status_code == 200
        assert response.text == _GAME_CLIENT_INDEX

    def test_play_page__when_index_missing__should_render_the_503_error_page(self, make_app, tmp_path):
        game_client_dir = tmp_path / "empty-game-dist"
        game_client_dir.mkdir()

        app = make_app(game_client_v2_dir=str(game_client_dir))
        with open_client(app) as c:
            register_with_csrf(c, "testuser")

            response = c.get("/play/test-game", headers={"accept": "text/html"})
            assert response.status_code == 503
            assert response.headers["content-type"].startswith("text/html")
            assert "Something went wrong" in response.text
            assert "Game client assets not available" not in response.text
            assert "Try again in a moment." in response.text
            assert 'href="/" role="button"' in response.text

    def test_game_assets_route__when_asset_requested__should_serve_it(self, client):
        response = client.get("/game-assets/v2/assets/index-v2.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        assert response.text == "console.log('game v2');"

    def test_game_assets_route__when_dir_missing__should_not_mount(self, make_app, tmp_path):
        app = make_app(game_client_v2_dir=str(tmp_path / "no-such-dir"))
        route_names = {r.name for r in app.routes}
        assert "game_assets" not in route_names

    def test_lobby_assets_route__when_asset_requested__should_serve_it(self, client):
        response = client.get("/lobby-assets/assets/lobby-test.js")
        assert response.status_code == 200
        assert response.text == "console.log('lobby');"

    def test_storybook_page__when_first_visit__should_set_csrf_cookie(self, app):
        with open_client(app) as c:
            response = c.get("/storybook")
            assert response.status_code == 200
            assert CSRF_COOKIE_NAME in response.cookies

    def test_storybook_page__when_visited__should_return_html(self, client):
        response = client.get("/storybook")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Lobby storybook" in response.text
        assert "Typography" in response.text
        assert "Buttons" in response.text
        assert "Table cards" in response.text


def test_legal_page__when_production__should_omit_storybook_links(
    make_app: Callable[..., Starlette],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("lobby.server.app.APP_VERSION", "1.0.0")
    with open_client(make_app()) as client:
        response = client.get("/terms")
        assert response.status_code == 200
        assert 'href="/storybook"' not in response.text
        assert 'href="/play/storybook"' not in response.text
        assert "footer-dev-links" not in response.text


def test_footer__when_production__should_link_version_to_its_github_release(
    make_app: Callable[..., Starlette],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("lobby.server.app.APP_VERSION", "1.0.0")
    with open_client(make_app()) as client:
        response = client.get("/terms")
        footer = response.text.split("<footer", 1)[1]
        assert '<a href="https://github.com/MahjongRepository/ronin/releases/tag/1.0.0"' in footer
        assert ">v1.0.0</a>" in footer


@pytest.mark.parametrize("path", ["/storybook", "/play/storybook", "/play/storybook/board"])
def test_storybook_page__when_production__should_return_not_found(
    make_app: Callable[..., Starlette],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
):
    monkeypatch.setattr("lobby.server.app.APP_VERSION", "1.0.0")
    with open_client(make_app()) as client:
        response = client.get(path)
        assert response.status_code == 404


_DEV_GAME_CLIENT_PAGE = '<script type="module" src="/game-assets/v2/@vite/client"></script>'


async def _dev_game_client_page(request):
    if "text/html" not in request.headers.get("accept", ""):
        return PlainTextResponse("not html", status_code=406)

    return HTMLResponse(_DEV_GAME_CLIENT_PAGE)


async def _dev_game_client_file(request):
    return PlainTextResponse(
        f"{request.path_params['path']}?{request.scope['query_string'].decode()}",
        media_type="text/javascript",
        headers={"etag": '"asset-etag"', "x-dev-only": "1"},
    )


_DEV_GAME_CLIENT_SERVER = Starlette(
    routes=[
        Route("/game-assets/v2/", _dev_game_client_page),
        Route("/game-assets/v2/{path:path}", _dev_game_client_file),
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
            game_client_v2_dev_url="http://localhost:5175",
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

    def test_play_page__when_dev_url_set__should_proxy_dev_server(self, client):
        page = client.get("/play/test-game")
        assert page.status_code == 200
        assert page.text == _DEV_GAME_CLIENT_PAGE

        asset = client.get("/game-assets/v2/src/index.ts")
        assert asset.status_code == 200
        assert asset.text == "src/index.ts?"

    def test_game_assets_route__when_game_client_v2_dev_url_set__should_proxy_encoded_path_and_query(self, client):
        response = client.get("/game-assets/v2/src/tile%23back.svg?import&t=1")
        assert response.status_code == 200
        assert response.text == "src/tile#back.svg?import&t=1"
        assert "javascript" in response.headers["content-type"]
        assert response.headers["etag"] == '"asset-etag"'
        assert "x-dev-only" not in response.headers

    def test_game_assets_route__when_dev_server_unreachable__should_return_a_plain_text_502(self, make_app):
        app = make_app(
            game_client_v2_dev_url="http://localhost:5175",
            game_client_dev_transport=httpx.MockTransport(_refuse_connection),
        )
        with open_client(app) as c:
            response = c.get("/game-assets/v2/src/index.ts", headers={"accept": "*/*"})
            assert (response.status_code, response.text) == (502, "Game client dev server not reachable")


class TestReplayPage:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "gamesuser")
        return client

    def test_replay_page__when_a_player_opens_a_link_without_a_seat__should_redirect_to_their_seat(self, client):
        now = datetime.now(UTC)
        client.app.state.game_repo.create_game(
            PlayedGame(
                game_id="seatless-link-game",
                started_at=now - timedelta(minutes=30),
                ended_at=now,
                end_reason=GameEndReason.COMPLETED,
                game_type="hanchan",
                standings=[
                    PlayedGameStanding(name="Tsumogiri 1", seat=0, score=41000, final_score=51),
                    PlayedGameStanding(
                        name="gamesuser", seat=2, user_id=session_user_id(client), score=27000, final_score=7
                    ),
                ],
            ),
        )

        seatless = client.get("/play/history/seatless-link-game?round=1&step=4", follow_redirects=False)
        seated = client.get("/play/history/seatless-link-game?seat=1", follow_redirects=False)
        other_game = client.get("/play/history/unknown-game", follow_redirects=False)

        assert seatless.status_code == 302
        assert seatless.headers["location"] == "/play/history/seatless-link-game?round=1&step=4&seat=2"
        assert seated.status_code == 200
        assert other_game.status_code == 200


def _grant_admin(client, *, username: str) -> None:
    with closing(sqlite3.connect(client.app.state.auth_settings.database_path)) as conn, conn:
        conn.execute(
            "UPDATE players SET data = json_set(data, '$.is_admin', json('true')) WHERE username = ?", (username,)
        )


def _shown_stats(page: str) -> dict[str, str]:
    return dict(re.findall(r'data-stat="(\w+)">([^<]*)<', page))


class TestMonitoringPage:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "opsuser")
        _grant_admin(client, username="opsuser")
        return client

    def test_monitoring_page__when_range_unknown__should_show_live_counts_and_the_default_ranges_games(
        self, client, game_server
    ):
        game_server.respond = lambda _request: httpx.Response(
            200, json={"status": "ok", "active_games": 1234, "pending_games": 2, "capacity_used": 1236}
        )
        now = datetime.now(UTC)
        game_repo = client.app.state.game_repo
        game_repo.finish_game(
            PlayedGame(
                game_id="two-days-ago",
                started_at=now - timedelta(days=2),
                ended_at=now - timedelta(days=2) + timedelta(minutes=10),
                end_reason=GameEndReason.COMPLETED,
            )
        )
        game_repo.finish_game(
            PlayedGame(
                game_id="today",
                started_at=now - timedelta(hours=2),
                ended_at=now - timedelta(hours=2) + timedelta(minutes=25, seconds=30),
                end_reason=GameEndReason.COMPLETED,
            )
        )
        game_repo.create_game(PlayedGame(game_id="playing", started_at=now - timedelta(minutes=5)))

        response = client.get("/admin/monitoring?range=forever")
        assert response.status_code == 200
        assert _shown_stats(response.text) == {
            "active": "1,234",
            "pending": "2",
            "started": "2",
            "completed": "1",
            "abandoned": "0",
            "error": "0",
            "unfinished": "1",
            "mean": "25m 30s",
            "median": "25m 30s",
            "p90": "25m 30s",
            "last_backup": "Unknown",
        }
        assert re.findall(r'<a href="\?range=(\w+)" class="monitoring-range" aria-current="page">', response.text) == [
            "24h"
        ]

    def test_monitoring_page__when_game_server_fails__should_show_live_counts_unavailable(self, client, game_server):
        game_server.respond = lambda _request: httpx.Response(500)

        response = client.get("/admin/monitoring?range=7d")
        assert response.status_code == 200
        assert "Unavailable: the game server did not answer" in response.text
        assert "No completed games in this range" in response.text
        assert _shown_stats(response.text) == {
            "started": "0",
            "completed": "0",
            "abandoned": "0",
            "error": "0",
            "unfinished": "0",
            "last_backup": "Unknown",
        }


class TestGameSessionRoute:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "alice")
        return client

    @pytest.fixture
    def user_id(self, client):
        return session_user_id(client)

    def test_game_session_route__when_user_is_playing__should_return_their_own_handoff_uncached(
        self, client, game_server, user_id
    ):
        looked_up: list[str] = []

        def answer_the_internal_caller(request: httpx.Request) -> httpx.Response:
            looked_up.append(request.url.path)
            if request.headers.get("authorization") != f"Bearer {client.app.state.settings.internal_api_secret}":
                return httpx.Response(401)

            return httpx.Response(200, json={"game_id": "game-1", "game_ticket": f"ticket-of-{request.url.path}"})

        game_server.respond = answer_the_internal_caller

        response = client.get("/api/game-session")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "game_id": "game-1",
            "ws_url": "wss://game-client.invalid/ws/game-1",
            "game_ticket": f"ticket-of-/players/{user_id}/game-session",
            "game_client_url": "/play",
        }
        assert looked_up == [f"/players/{user_id}/game-session"]

    def test_game_session_route__when_no_game_or_lookup_fails__should_tell_them_apart(self, client, game_server):
        game_server.respond = lambda _request: httpx.Response(404)
        missing = client.get("/api/game-session")
        assert (missing.status_code, missing.json()) == (404, {"error": "not_playing"})

        game_server.respond = lambda _request: httpx.Response(500)
        failed = client.get("/api/game-session")
        assert (failed.status_code, failed.json()) == (503, {"error": "game_lookup_failed"})
