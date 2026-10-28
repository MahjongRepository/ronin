import asyncio
import gzip

import httpx
import pytest

from lobby import game_transition
from shared.storage import read_replay, replay_file_path


def _refuse_connection(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("game server down", request=request)


def _write_gzip_replay(replay_dir, game_id, content):
    target = replay_file_path(replay_dir, game_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    compressed = gzip.compress(content.encode("utf-8"))
    target.write_bytes(compressed)


class TestReplayContent:
    @pytest.fixture
    def replay_dir(self, tmp_path):
        replay_dir = tmp_path / "replays"
        replay_dir.mkdir()
        return replay_dir

    @pytest.fixture
    def app(self, make_app, tmp_path, replay_dir):
        game_client_dir = tmp_path / "game-dist"
        game_client_dir.mkdir()
        return make_app(replay_dir=str(replay_dir), game_client_dir=str(game_client_dir))

    @pytest.fixture
    def setup(self, client, replay_dir):
        return client, replay_dir

    def test_replay_route__when_replay_exists__should_return_200_with_content(self, setup):
        client, replay_dir = setup
        ndjson = '{"version":"0.3-dev"}\n{"t":1,"sd":"abc"}'
        _write_gzip_replay(replay_dir=replay_dir, game_id="game-123", content=ndjson)

        response = client.get("/api/replays/game-123")
        assert response.status_code == 200
        assert response.text == ndjson

    def test_replay_route__should_set_gzip_content_encoding(self, setup):
        client, replay_dir = setup
        _write_gzip_replay(replay_dir=replay_dir, game_id="game-456", content='{"version":"0.3-dev"}')

        # Use raw transport to inspect headers before decompression
        response = client.get("/api/replays/game-456")
        assert response.status_code == 200
        assert response.headers["content-encoding"] == "gzip"

    def test_replay_route__should_set_immutable_cache_headers(self, setup):
        client, replay_dir = setup
        _write_gzip_replay(replay_dir=replay_dir, game_id="game-789", content='{"version":"0.3-dev"}')

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
        assert response.status_code == 404

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
        _write_gzip_replay(replay_dir=replay_dir, game_id=game_id, content='{"version":"0.3-dev"}')

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

    def test_read_replay__when_symlink_escapes_replay_dir__should_return_none(self, setup, tmp_path):
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
        result = read_replay(str(replay_dir), game_id)
        assert result is None

    def test_tenhou_replay_route__when_game_server_converts__should_serve_its_xml_as_a_download(
        self, client, game_server
    ):
        asked: list[str] = []

        def convert_for_the_internal_caller(request: httpx.Request) -> httpx.Response:
            asked.append(request.url.path)
            if request.headers.get("authorization") != f"Bearer {client.app.state.settings.internal_api_secret}":
                return httpx.Response(401)

            return httpx.Response(200, content=b'<mjloggm ver="2.3"></mjloggm>')

        game_server.respond = convert_for_the_internal_caller

        response = client.get("/api/replays/game-123/tenhou.xml")
        assert response.status_code == 200
        assert response.text == '<mjloggm ver="2.3"></mjloggm>'
        assert response.headers["content-type"] == "application/xml"
        assert response.headers["content-disposition"] == 'attachment; filename="game-123.xml"'
        assert asked == ["/replays/game-123/tenhou"]

    def test_tenhou_replay_route__when_missing_invalid_or_failed__should_tell_them_apart(self, client, game_server):
        asked: list[str] = []

        def answer(status_code: int):
            def respond(request: httpx.Request) -> httpx.Response:
                asked.append(request.url.path)
                return httpx.Response(status_code)

            return respond

        game_server.respond = answer(404)
        missing = client.get("/api/replays/game-123/tenhou.xml")
        assert missing.status_code == 404
        assert "cache-control" not in missing.headers

        invalid = client.get("/api/replays/game%3Cscript%3E/tenhou.xml")
        assert invalid.status_code == 404
        assert asked == ["/replays/game-123/tenhou"]

        game_server.respond = answer(422)
        unfinished = client.get("/api/replays/game-123/tenhou.xml")
        assert unfinished.status_code == 422
        assert "cache-control" not in unfinished.headers

        game_server.respond = answer(500)
        failed = client.get("/api/replays/game-123/tenhou.xml")
        assert failed.status_code == 502
        assert "cache-control" not in failed.headers

        game_server.respond = _refuse_connection
        unreachable = client.get("/api/replays/game-123/tenhou.xml")
        assert unreachable.status_code == 502

    def test_tenhou_replay_route__when_game_server_exceeds_the_deadline__should_answer_502(
        self, client, game_server, monkeypatch
    ):
        monkeypatch.setattr(game_transition, "_REPLAY_EXPORT_TIMEOUT_SECONDS", 0.01)

        async def never_answer(_request: httpx.Request) -> httpx.Response:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        game_server.respond = never_answer

        response = client.get("/api/replays/game-123/tenhou.xml")
        assert response.status_code == 502

    def test_replay_page_route__should_serve_play_page(self, setup):
        client, _replay_dir = setup
        response = client.get("/play/history/game-123")
        assert response.status_code == 503

    def test_replay_page_route__when_unauthenticated__should_not_redirect_to_login(self, setup):
        client, _replay_dir = setup
        # No login — should still get 503 (not 303 redirect to login)
        response = client.get("/play/history/game-123", follow_redirects=False)
        assert response.status_code == 503
