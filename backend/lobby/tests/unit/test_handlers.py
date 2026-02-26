"""Tests for lobby handler utility functions."""

import json

import pytest

from lobby.views.handlers import load_vite_manifest, resolve_vite_asset_urls


class TestLoadViteManifest:
    def test_missing_manifest_returns_empty_dict(self, tmp_path):
        assert load_vite_manifest(str(tmp_path)) == {}

    def test_malformed_json_raises_value_error(self, tmp_path):
        vite_dir = tmp_path / ".vite"
        vite_dir.mkdir()
        (vite_dir / "manifest.json").write_text("not valid json{{{")
        with pytest.raises(ValueError, match=r"Malformed manifest\.json"):
            load_vite_manifest(str(tmp_path))

    def test_non_dict_json_raises_type_error(self, tmp_path):
        vite_dir = tmp_path / ".vite"
        vite_dir.mkdir()
        (vite_dir / "manifest.json").write_text('["not", "a", "dict"]')
        with pytest.raises(TypeError, match=r"must be a JSON object"):
            load_vite_manifest(str(tmp_path))

    def test_valid_manifest_returns_dict(self, tmp_path):
        vite_dir = tmp_path / ".vite"
        vite_dir.mkdir()
        manifest = {"src/index.ts": {"file": "assets/game-abc.js", "isEntry": True}}
        (vite_dir / "manifest.json").write_text(json.dumps(manifest))
        assert load_vite_manifest(str(tmp_path)) == manifest


class TestResolveViteAssetUrls:
    def test_empty_manifest(self):
        assert resolve_vite_asset_urls({}) == {}

    def test_full_manifest(self):
        manifest = {
            "src/index.ts": {
                "file": "assets/game-abc123.js",
                "css": ["assets/game-def456.css"],
                "isEntry": True,
            },
            "src/lobby/index.ts": {
                "file": "assets/lobby-ghi789.js",
                "css": ["assets/lobby-jkl012.css"],
                "isEntry": True,
            },
        }
        urls = resolve_vite_asset_urls(manifest)
        assert urls["game_js"] == "/game-assets/assets/game-abc123.js"
        assert urls["game_css"] == "/game-assets/assets/game-def456.css"
        assert urls["lobby_js"] == "/game-assets/assets/lobby-ghi789.js"
        assert urls["lobby_css"] == "/game-assets/assets/lobby-jkl012.css"

    def test_lobby_entry_css_extracted(self):
        """Lobby entry produces both JS and extracted CSS."""
        manifest = {
            "src/lobby/index.ts": {
                "file": "assets/lobby-abc123.js",
                "css": ["assets/lobby-def456.css"],
                "isEntry": True,
            },
        }
        urls = resolve_vite_asset_urls(manifest)
        assert urls["lobby_js"] == "/game-assets/assets/lobby-abc123.js"
        assert urls["lobby_css"] == "/game-assets/assets/lobby-def456.css"

    def test_partial_manifest_no_file_key(self):
        """Entry without 'file' key is skipped gracefully (no KeyError)."""
        manifest = {
            "src/index.ts": {"isEntry": True},
        }
        urls = resolve_vite_asset_urls(manifest)
        assert "game_js" not in urls

    def test_partial_manifest_missing_entries(self):
        """Only present entries are resolved."""
        manifest = {
            "src/index.ts": {
                "file": "assets/game.js",
                "css": ["assets/game.css"],
                "isEntry": True,
            },
        }
        urls = resolve_vite_asset_urls(manifest)
        assert "game_js" in urls
        assert "lobby_js" not in urls
        assert "lobby_css" not in urls
