"""Tests for lobby handler utility functions."""

import pytest

from lobby.views.handlers import build_websocket_url, load_game_assets_manifest


class TestBuildWebsocketUrl:
    def test_http_to_ws(self):
        assert build_websocket_url("http://localhost:8711", "room1") == "ws://localhost:8711/ws/room1"

    def test_https_to_wss(self):
        assert build_websocket_url("https://example.com", "room1") == "wss://example.com/ws/room1"


class TestLoadGameAssetsManifest:
    def test_missing_manifest_returns_empty_dict(self, tmp_path):
        assert load_game_assets_manifest(str(tmp_path)) == {}

    def test_malformed_json_raises_value_error(self, tmp_path):
        (tmp_path / "manifest.json").write_text("not valid json{{{")
        with pytest.raises(ValueError, match=r"Malformed manifest\.json"):
            load_game_assets_manifest(str(tmp_path))

    def test_non_dict_json_raises_type_error(self, tmp_path):
        (tmp_path / "manifest.json").write_text('["not", "a", "dict"]')
        with pytest.raises(TypeError, match=r"must be a JSON object"):
            load_game_assets_manifest(str(tmp_path))
