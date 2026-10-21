import json
from datetime import UTC, datetime, timedelta

import pytest

from lobby.views.assets import load_vite_manifest, resolve_vite_asset_urls
from lobby.views.history_handlers import _format_duration, _prepare_history_for_display
from shared.dal.models import PlayedGame, PlayedGameStanding


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

    def test_resolve_vite_asset_urls__when_full_manifest__should_resolve_game_and_lobby_urls(self):
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

    def test_resolve_vite_asset_urls__when_lobby_entry_only__should_resolve_lobby_js_and_css(self):
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

    def test_resolve_vite_asset_urls__when_entry_has_no_file__should_omit_game_js(self):
        manifest = {
            "src/index.ts": {"isEntry": True},
        }
        urls = resolve_vite_asset_urls(manifest)
        assert "game_js" not in urls

    def test_resolve_vite_asset_urls__when_lobby_entry_missing__should_omit_lobby_urls(self):
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


class TestFormatDuration:
    def test_format_duration__when_under_a_minute__should_show_seconds(self):
        now = datetime.now(UTC)
        assert _format_duration(now - timedelta(seconds=45), now) == "45s"

    def test_format_duration__when_zero__should_show_0s(self):
        now = datetime.now(UTC)
        assert _format_duration(now, now) == "0s"

    def test_format_duration__when_minutes_and_seconds__should_show_both(self):
        now = datetime.now(UTC)
        assert _format_duration(now - timedelta(minutes=5, seconds=30), now) == "5m 30s"

    def test_format_duration__when_exact_minutes__should_show_zero_seconds(self):
        now = datetime.now(UTC)
        assert _format_duration(now - timedelta(minutes=10), now) == "10m 0s"

    def test_format_duration__when_over_an_hour__should_show_hours_and_minutes(self):
        now = datetime.now(UTC)
        assert _format_duration(now - timedelta(hours=1, minutes=12), now) == "1h 12m"


def _make_standing(
    name: str,
    seat: int,
    score: int | None = None,
    final_score: int | None = None,
) -> PlayedGameStanding:
    return PlayedGameStanding(name=name, seat=seat, user_id="", score=score, final_score=final_score)


class TestPrepareGamesForDisplay:
    def test_prepare_history_for_display__when_game_completed__should_mark_winner_and_labels(self):
        now = datetime.now(UTC)
        game = PlayedGame(
            game_id="game-1",
            started_at=now - timedelta(minutes=30),
            ended_at=now,
            end_reason="completed",
            game_type="hanchan",
            num_rounds_played=8,
            standings=[
                _make_standing(name="Alice", seat=0, score=35000, final_score=30),
                _make_standing(name="Bob", seat=1, score=25000, final_score=0),
                _make_standing(name="Charlie", seat=2, score=22000, final_score=-10),
                _make_standing(name="Diana", seat=3, score=18000, final_score=-20),
            ],
        )
        result = _prepare_history_for_display([game])
        assert len(result) == 1
        entry = result[0]
        assert entry["players"][0]["is_winner"] is True
        assert entry["players"][0]["name"] == "Alice"
        assert entry["players"][0]["score"] == 35000
        assert entry["players"][1]["score"] == 25000
        assert entry["players"][1]["is_winner"] is False
        assert entry["status"] == "completed"
        assert entry["game_type_label"] == "南"
        assert entry["duration_label"] == "30m 0s"

    def test_prepare_history_for_display__when_game_in_progress__should_have_no_winner(self):
        now = datetime.now(UTC)
        game = PlayedGame(
            game_id="game-2",
            started_at=now,
            standings=[
                _make_standing(name="Alice", seat=0),
                _make_standing(name="Bob", seat=1),
            ],
        )
        result = _prepare_history_for_display([game])
        entry = result[0]
        assert all(not p["is_winner"] for p in entry["players"])
        assert entry["status"] == "active"
        assert entry["duration_label"] is None

    def test_prepare_history_for_display__when_game_abandoned__should_show_active_status(self):
        now = datetime.now(UTC)
        game = PlayedGame(
            game_id="game-3",
            started_at=now - timedelta(minutes=5),
            ended_at=now,
            end_reason="abandoned",
            standings=[_make_standing(name="Alice", seat=0), _make_standing(name="Bot-1", seat=1)],
        )
        result = _prepare_history_for_display([game])
        entry = result[0]
        assert entry["status"] == "active"
        assert all(not p["is_winner"] for p in entry["players"])
        assert entry["duration_label"] == "5m 0s"

    def test_prepare_history_for_display__when_tonpusen__should_label_east(self):
        now = datetime.now(UTC)
        game = PlayedGame(game_id="g", started_at=now, game_type="tonpusen")
        result = _prepare_history_for_display([game])
        assert result[0]["game_type_label"] == "東"

    def test_prepare_history_for_display__when_game_type_unknown__should_use_empty_label(self):
        now = datetime.now(UTC)
        game = PlayedGame(game_id="g", started_at=now, game_type="")
        result = _prepare_history_for_display([game])
        assert result[0]["game_type_label"] == ""

    def test_prepare_history_for_display__when_game_under_a_minute__should_show_seconds(self):
        now = datetime.now(UTC)
        game = PlayedGame(
            game_id="g",
            started_at=now - timedelta(seconds=30),
            ended_at=now,
            end_reason="completed",
        )
        result = _prepare_history_for_display([game])
        assert result[0]["duration_label"] == "30s"

    def test_prepare_history_for_display__when_standings_empty__should_have_no_players(self):
        now = datetime.now(UTC)
        game = PlayedGame(game_id="g", started_at=now, standings=[])
        result = _prepare_history_for_display([game])
        assert result[0]["players"] == []
