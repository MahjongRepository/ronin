import json
from datetime import UTC, datetime

import pytest

from lobby.dal.models import PlayedGame, PlayedGameStanding
from lobby.views.assets import load_vite_manifest, resolve_vite_asset_urls
from lobby.views.history_handlers import history_entries

_VIEWER_USER_ID = "viewer-user-id"


class TestLoadViteManifest:
    def test_load_vite_manifest__when_manifest_missing__should_return_empty_dict(self, tmp_path):
        assert load_vite_manifest(str(tmp_path)) == {}

    def test_load_vite_manifest__when_json_malformed__should_raise_value_error(self, tmp_path):
        vite_dir = tmp_path / ".vite"
        vite_dir.mkdir()
        (vite_dir / "manifest.json").write_text("not valid json{{{")

        with pytest.raises(ValueError, match=r"Malformed manifest\.json"):
            load_vite_manifest(str(tmp_path))

    def test_load_vite_manifest__when_json_not_object__should_raise_type_error(self, tmp_path):
        vite_dir = tmp_path / ".vite"
        vite_dir.mkdir()
        (vite_dir / "manifest.json").write_text('["not", "a", "dict"]')

        with pytest.raises(TypeError, match=r"must be a JSON object"):
            load_vite_manifest(str(tmp_path))

    def test_load_vite_manifest__when_manifest_valid__should_return_dict(self, tmp_path):
        vite_dir = tmp_path / ".vite"
        vite_dir.mkdir()
        manifest = {"src/index.ts": {"file": "assets/game-abc.js", "isEntry": True}}
        (vite_dir / "manifest.json").write_text(json.dumps(manifest))

        assert load_vite_manifest(str(tmp_path)) == manifest


class TestResolveViteAssetUrls:
    def test_resolve_vite_asset_urls__when_manifest_empty__should_return_empty_dict(self):
        assert resolve_vite_asset_urls({}) == {}

    def test_resolve_vite_asset_urls__when_lobby_entry_built__should_resolve_lobby_js_and_css(self):
        manifest = {
            "src/index.ts": {
                "file": "assets/lobby-abc123.js",
                "css": ["assets/lobby-def456.css"],
                "isEntry": True,
            },
        }

        urls = resolve_vite_asset_urls(manifest)
        assert urls == {
            "lobby_js": "/lobby-assets/assets/lobby-abc123.js",
            "lobby_css": "/lobby-assets/assets/lobby-def456.css",
        }

    def test_resolve_vite_asset_urls__when_entry_has_no_file__should_omit_lobby_js(self):
        manifest = {
            "src/index.ts": {"isEntry": True},
        }

        urls = resolve_vite_asset_urls(manifest)
        assert "lobby_js" not in urls


def _make_standing(
    name: str,
    seat: int,
    score: int | None = None,
    final_score: int | None = None,
    user_id: str = "",
) -> PlayedGameStanding:
    return PlayedGameStanding(name=name, seat=seat, user_id=user_id, score=score, final_score=final_score)


class TestHistoryEntries:
    def test_history_entries__when_viewer_did_not_play__should_link_without_seat(self):
        game = PlayedGame(
            game_id="game-1",
            started_at=datetime.now(UTC),
            standings=[
                _make_standing(name="Alice", seat=2, user_id="alice-user-id"),
                _make_standing(name="Bob", seat=0, user_id=_VIEWER_USER_ID),
            ],
        )

        [entry] = history_entries([game], user_id="onlooker-user-id")
        assert [player["is_viewer"] for player in entry["players"]] == [False, False]
        assert entry["viewer_replay_url"] == "/play/history/game-1"

    def test_history_entries__when_start_stored_without_offset__should_send_it_as_utc(self):
        game = PlayedGame(
            game_id="g",
            started_at=datetime(2026, 10, 24, 3, 9, tzinfo=UTC).replace(tzinfo=None),
            ended_at=datetime(2026, 10, 24, 3, 54, tzinfo=UTC),
        )

        [entry] = history_entries([game], user_id=_VIEWER_USER_ID)
        assert entry["started_at"] == "2026-10-24T03:09:00+00:00"
        assert entry["duration_seconds"] == 2700.0

    def test_history_entries__when_tonpusen__should_carry_the_east_wind(self):
        game = PlayedGame(game_id="g", started_at=datetime.now(UTC), game_type="tonpusen")

        [entry] = history_entries([game], user_id=_VIEWER_USER_ID)
        assert (entry["game_type"], entry["wind"]) == ("tonpusen", "東")

    def test_history_entries__when_game_type_unknown__should_have_no_wind(self):
        game = PlayedGame(game_id="g", started_at=datetime.now(UTC), game_type="")

        [entry] = history_entries([game], user_id=_VIEWER_USER_ID)
        assert entry["wind"] is None

    def test_history_entries__when_standings_empty__should_have_no_players(self):
        game = PlayedGame(game_id="g", started_at=datetime.now(UTC), standings=[])

        [entry] = history_entries([game], user_id=_VIEWER_USER_ID)
        assert entry["players"] == []
