"""Tests for lobby handler utility functions."""

import pytest

from lobby.views.handlers import load_game_assets_manifest


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
