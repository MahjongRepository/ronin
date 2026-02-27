"""Tests for lobby handler utility functions."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from lobby.views.handlers import (
    _format_duration,
    _prepare_history_for_display,
    load_vite_manifest,
    resolve_vite_asset_urls,
)
from shared.dal.models import PlayedGame, PlayedGameStanding


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


class TestFormatDuration:
    def test_seconds_only(self):
        now = datetime.now(UTC)
        assert _format_duration(now - timedelta(seconds=45), now) == "45s"

    def test_zero_seconds(self):
        now = datetime.now(UTC)
        assert _format_duration(now, now) == "0s"

    def test_minutes_and_seconds(self):
        now = datetime.now(UTC)
        assert _format_duration(now - timedelta(minutes=5, seconds=30), now) == "5m 30s"

    def test_exact_minutes(self):
        now = datetime.now(UTC)
        assert _format_duration(now - timedelta(minutes=10), now) == "10m 0s"

    def test_hours_and_minutes(self):
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
    def test_completed_game_identifies_winner(self):
        """First player in standings (placement order) is marked as winner."""
        now = datetime.now(UTC)
        game = PlayedGame(
            game_id="game-1",
            started_at=now - timedelta(minutes=30),
            ended_at=now,
            end_reason="completed",
            game_type="hanchan",
            num_rounds_played=8,
            standings=[
                _make_standing("Alice", 0, score=35000, final_score=30),
                _make_standing("Bob", 1, score=25000, final_score=0),
                _make_standing("Charlie", 2, score=22000, final_score=-10),
                _make_standing("Diana", 3, score=18000, final_score=-20),
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

    def test_in_progress_game_has_no_winner(self):
        """Games without scores (in progress) have no winner and active status."""
        now = datetime.now(UTC)
        game = PlayedGame(
            game_id="game-2",
            started_at=now,
            standings=[
                _make_standing("Alice", 0),
                _make_standing("Bob", 1),
            ],
        )
        result = _prepare_history_for_display([game])
        entry = result[0]
        assert all(not p["is_winner"] for p in entry["players"])
        assert entry["status"] == "active"
        assert entry["duration_label"] is None

    def test_abandoned_game_status(self):
        """Abandoned games show 'active' status and preserve standings without scores."""
        now = datetime.now(UTC)
        game = PlayedGame(
            game_id="game-3",
            started_at=now - timedelta(minutes=5),
            ended_at=now,
            end_reason="abandoned",
            standings=[_make_standing("Alice", 0), _make_standing("Bot-1", 1)],
        )
        result = _prepare_history_for_display([game])
        entry = result[0]
        assert entry["status"] == "active"
        assert all(not p["is_winner"] for p in entry["players"])
        assert entry["duration_label"] == "5m 0s"

    def test_tonpusen_game_type_label(self):
        now = datetime.now(UTC)
        game = PlayedGame(game_id="g", started_at=now, game_type="tonpusen")
        result = _prepare_history_for_display([game])
        assert result[0]["game_type_label"] == "東"

    def test_unknown_game_type_label_is_empty(self):
        now = datetime.now(UTC)
        game = PlayedGame(game_id="g", started_at=now, game_type="")
        result = _prepare_history_for_display([game])
        assert result[0]["game_type_label"] == ""

    def test_short_duration_shows_seconds(self):
        """Games lasting under 60 seconds display in seconds."""
        now = datetime.now(UTC)
        game = PlayedGame(
            game_id="g",
            started_at=now - timedelta(seconds=30),
            ended_at=now,
            end_reason="completed",
        )
        result = _prepare_history_for_display([game])
        assert result[0]["duration_label"] == "30s"

    def test_empty_standings_produces_no_players(self):
        """Games with no standings (e.g. game state was unavailable) produce an empty players list."""
        now = datetime.now(UTC)
        game = PlayedGame(game_id="g", started_at=now, standings=[])
        result = _prepare_history_for_display([game])
        assert result[0]["players"] == []
