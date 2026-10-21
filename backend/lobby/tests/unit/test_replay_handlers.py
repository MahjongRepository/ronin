import gzip

import pytest
from starlette.testclient import TestClient

from lobby.server.app import create_app
from lobby.settings import LobbyServerSettings
from lobby.views.replay_handlers import _load_replay
from shared.auth.settings import AuthSettings
from shared.storage import replay_file_path


def _make_client(tmp_path):
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir()

    static_dir = tmp_path / "public"
    static_dir.mkdir()
    game_assets_dir = tmp_path / "dist"
    game_assets_dir.mkdir()

    app = create_app(
        settings=LobbyServerSettings(
            replay_dir=str(replay_dir),
            static_dir=str(static_dir),
            game_assets_dir=str(game_assets_dir),
        ),
        auth_settings=AuthSettings(
            game_ticket_secret="test-secret",
            database_path=str(tmp_path / "test.db"),
            cookie_secure=False,
        ),
    )
    return TestClient(app), replay_dir


def _write_gzip_replay(replay_dir, game_id, content):
    target = replay_file_path(replay_dir, game_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    compressed = gzip.compress(content.encode("utf-8"))
    target.write_bytes(compressed)


class TestReplayContent:
    @pytest.fixture
    def setup(self, tmp_path):
        client, replay_dir = _make_client(tmp_path)
        yield client, replay_dir
        client.app.state.db.close()

    def test_replay_route__when_replay_exists__should_return_200_with_content(self, setup):
        client, replay_dir = setup
        ndjson = '{"version":"0.3-dev"}\n{"t":1,"sd":"abc"}'
        _write_gzip_replay(replay_dir, "game-123", ndjson)

        response = client.get("/api/replays/game-123")
        assert response.status_code == 200
        assert response.text == ndjson

    def test_replay_route__should_set_gzip_content_encoding(self, setup):
        client, replay_dir = setup
        _write_gzip_replay(replay_dir, "game-456", '{"version":"0.3-dev"}')

        # Use raw transport to inspect headers before decompression
        response = client.get("/api/replays/game-456")
        assert response.status_code == 200
        assert response.headers["content-encoding"] == "gzip"

    def test_replay_route__should_set_immutable_cache_headers(self, setup):
        client, replay_dir = setup
        _write_gzip_replay(replay_dir, "game-789", '{"version":"0.3-dev"}')

        response = client.get("/api/replays/game-789")
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"

    def test_replay_route__when_game_missing__should_return_404(self, setup):
        client, _replay_dir = setup
        response = client.get("/api/replays/nonexistent")
        assert response.status_code == 404

    def test_replay_route__when_game_missing__should_omit_cache_headers(self, setup):
        client, _replay_dir = setup
        response = client.get("/api/replays/nonexistent")
        assert "cache-control" not in response.headers

    def test_replay_route__when_game_id_empty__should_not_serve_replay(self, setup):
        client, _replay_dir = setup
        response = client.get("/api/replays/")
        assert response.status_code in {404, 307}

    def test_replay_route__when_game_id_has_special_chars__should_return_404(self, setup):
        client, _replay_dir = setup
        response = client.get("/api/replays/game<script>")
        assert response.status_code == 404

    def test_replay_route__when_game_id_is_dots__should_return_404(self, setup):
        client, _replay_dir = setup
        response = client.get("/api/replays/..")
        assert response.status_code == 404

    def test_replay_route__when_game_id_too_long__should_return_404(self, setup):
        client, _replay_dir = setup
        response = client.get(f"/api/replays/{'a' * 51}")
        assert response.status_code == 404

    def test_replay_route__when_game_id_too_short__should_return_404(self, setup):
        client, _replay_dir = setup
        response = client.get("/api/replays/abc")
        assert response.status_code == 404

    def test_replay_route__when_game_id_at_max_length__should_return_200(self, setup):
        client, replay_dir = setup
        game_id = "a" * 50
        _write_gzip_replay(replay_dir, game_id, '{"version":"0.3-dev"}')

        response = client.get(f"/api/replays/{game_id}")
        assert response.status_code == 200

    def test_replay_route__when_game_id_has_encoded_traversal__should_return_404(self, setup):
        client, _replay_dir = setup
        # %2F is / which Starlette may or may not decode, but the regex rejects it
        response = client.get("/api/replays/foo%2F..%2Fbar")
        assert response.status_code == 404

    def test_replay_route__when_file_oversized__should_return_404(self, setup):
        client, replay_dir = setup
        game_id = "big-game"
        target = replay_file_path(replay_dir, game_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write raw bytes > 1 MB (not valid gzip, but size check happens first)
        target.write_bytes(b"\x00" * (1_048_576 + 1))

        response = client.get(f"/api/replays/{game_id}")
        assert response.status_code == 404

    def test_replay_route__when_file_unreadable__should_return_404(self, setup):
        client, replay_dir = setup
        game_id = "broken_file"
        target = replay_file_path(replay_dir, game_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.mkdir()  # directory, not a file — read will fail

        response = client.get(f"/api/replays/{game_id}")
        assert response.status_code == 404

    def test_load_replay__when_symlink_escapes_replay_dir__should_return_none(self, setup, tmp_path):
        _client, replay_dir = setup
        game_id = "escape_link"
        # Create a file outside the replay dir
        outside = tmp_path / "secret.txt.gz"
        outside.write_bytes(gzip.compress(b"secret"))
        # Create a symlink at the sharded path pointing outside
        target = replay_file_path(replay_dir, game_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(outside)

        # Call the sync helper directly — the symlink resolves outside replay_dir
        result = _load_replay(str(replay_dir), game_id)
        assert result is None

    def test_replay_page_route__should_serve_play_page(self, setup):
        client, _replay_dir = setup
        response = client.get("/play/history/game-123")
        # Without game assets built, play_page returns 503
        assert response.status_code == 503

    def test_replay_page_route__when_unauthenticated__should_not_redirect_to_login(self, setup):
        client, _replay_dir = setup
        # No login — should still get 503 (not 303 redirect to login)
        response = client.get("/play/history/game-123", follow_redirects=False)
        assert response.status_code == 503
