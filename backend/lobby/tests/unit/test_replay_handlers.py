"""Tests for the replay API handler."""

import gzip

import pytest
from starlette.testclient import TestClient

from lobby.server.app import create_app
from lobby.server.settings import LobbyServerSettings
from lobby.views.replay_handlers import _load_replay
from shared.auth.settings import AuthSettings


def _make_client(tmp_path):
    """Create a lobby TestClient with a temporary replay directory."""
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
    """Write a gzip-compressed replay file."""
    compressed = gzip.compress(content.encode("utf-8"))
    (replay_dir / f"{game_id}.txt.gz").write_bytes(compressed)


class TestReplayContent:
    @pytest.fixture
    def setup(self, tmp_path):
        client, replay_dir = _make_client(tmp_path)
        yield client, replay_dir
        client.app.state.db.close()

    def test_existing_replay_returns_200_with_content(self, setup):
        client, replay_dir = setup
        ndjson = '{"version":"0.3-dev"}\n{"t":1,"sd":"abc"}'
        _write_gzip_replay(replay_dir, "game-123", ndjson)

        response = client.get("/api/replays/game-123")
        assert response.status_code == 200
        assert response.text == ndjson

    def test_response_includes_gzip_content_encoding(self, setup):
        client, replay_dir = setup
        _write_gzip_replay(replay_dir, "game-456", '{"version":"0.3-dev"}')

        # Use raw transport to inspect headers before decompression
        response = client.get("/api/replays/game-456")
        assert response.status_code == 200
        assert response.headers["content-encoding"] == "gzip"

    def test_response_includes_cache_headers(self, setup):
        client, replay_dir = setup
        _write_gzip_replay(replay_dir, "game-789", '{"version":"0.3-dev"}')

        response = client.get("/api/replays/game-789")
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"

    def test_nonexistent_game_returns_404(self, setup):
        client, _replay_dir = setup
        response = client.get("/api/replays/nonexistent")
        assert response.status_code == 404

    def test_404_response_has_no_cache_headers(self, setup):
        """Error responses must not include immutable cache headers."""
        client, _replay_dir = setup
        response = client.get("/api/replays/nonexistent")
        assert "cache-control" not in response.headers

    def test_empty_game_id_returns_404(self, setup):
        """Starlette router won't match empty game_id, but handler rejects it too."""
        client, _replay_dir = setup
        response = client.get("/api/replays/")
        assert response.status_code in {404, 307}

    def test_game_id_with_special_chars_returns_404(self, setup):
        client, _replay_dir = setup
        response = client.get("/api/replays/game<script>")
        assert response.status_code == 404

    def test_game_id_with_dots_returns_404(self, setup):
        """Reject '..' even though path traversal check would also catch it."""
        client, _replay_dir = setup
        response = client.get("/api/replays/..")
        assert response.status_code == 404

    def test_game_id_too_long_returns_404(self, setup):
        client, _replay_dir = setup
        response = client.get(f"/api/replays/{'a' * 51}")
        assert response.status_code == 404

    def test_game_id_at_max_length_is_accepted(self, setup):
        """A 50-char game_id should be accepted (if file exists)."""
        client, replay_dir = setup
        game_id = "a" * 50
        _write_gzip_replay(replay_dir, game_id, '{"version":"0.3-dev"}')

        response = client.get(f"/api/replays/{game_id}")
        assert response.status_code == 200

    def test_game_id_with_url_encoded_traversal_returns_404(self, setup):
        """URL-encoded path traversal attempts are rejected by regex validation."""
        client, _replay_dir = setup
        # %2F is / which Starlette may or may not decode, but the regex rejects it
        response = client.get("/api/replays/foo%2F..%2Fbar")
        assert response.status_code == 404

    def test_oversized_file_returns_404(self, setup):
        """Files exceeding 1 MB on disk are rejected."""
        client, replay_dir = setup
        # Write raw bytes > 1 MB (not valid gzip, but size check happens first)
        (replay_dir / "big-game.txt.gz").write_bytes(b"\x00" * (1_048_576 + 1))

        response = client.get("/api/replays/big-game")
        assert response.status_code == 404

    def test_unreadable_file_returns_404(self, setup):
        """Files that exist but can't be read return 404."""
        client, replay_dir = setup
        target = replay_dir / "broken.txt.gz"
        target.mkdir()  # directory, not a file — read_bytes will fail

        response = client.get("/api/replays/broken")
        assert response.status_code == 404

    def test_path_traversal_via_symlink_returns_404(self, setup, tmp_path):
        """A game_id whose resolved path escapes the replay dir is rejected."""
        _client, replay_dir = setup
        # Create a file outside the replay dir
        outside = tmp_path / "secret.txt.gz"
        outside.write_bytes(gzip.compress(b"secret"))
        # Create a symlink inside the replay dir pointing outside
        link = replay_dir / "escape.txt.gz"
        link.symlink_to(outside)

        # Call the sync helper directly — the symlink resolves outside replay_dir
        result = _load_replay(str(replay_dir), "escape")
        assert result is None

    def test_replay_page_route_serves_play_page(self, setup):
        """GET /play/history/{game_id} serves the game client page (or 503 if no assets)."""
        client, _replay_dir = setup
        response = client.get("/play/history/game-123")
        # Without game assets built, play_page returns 503
        assert response.status_code == 503

    def test_replay_page_route_is_public(self, setup):
        """The /play/history/{game_id} route does not require authentication."""
        client, _replay_dir = setup
        # No login — should still get 503 (not 303 redirect to login)
        response = client.get("/play/history/game-123", follow_redirects=False)
        assert response.status_code == 503
