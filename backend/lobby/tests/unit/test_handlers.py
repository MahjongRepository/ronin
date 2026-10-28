import functools
import json
from datetime import UTC, datetime, timedelta

import pytest

from lobby.i18n import Locale, Translator, load_catalogs
from lobby.views.assets import load_vite_manifest, resolve_vite_asset_urls
from lobby.views.history_handlers import _format_duration, _prepare_history_for_display
from shared.dal.models import PlayedGame, PlayedGameStanding

_VIEWER_USER_ID = "viewer-user-id"
_TRANSLATOR = Translator(catalogs=load_catalogs(), strict=True)

translate_en = functools.partial(_TRANSLATOR.translate, Locale.EN)


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


class TestFormatDuration:
    def test_format_duration__when_under_a_minute__should_show_seconds(self):
        now = datetime.now(UTC)
        assert _format_duration(now - timedelta(seconds=45), now, translate=translate_en) == "45s"

    def test_format_duration__when_zero__should_show_0s(self):
        now = datetime.now(UTC)
        assert _format_duration(now, now, translate=translate_en) == "0s"

    def test_format_duration__when_minutes_and_seconds__should_show_both(self):
        now = datetime.now(UTC)
        assert _format_duration(now - timedelta(minutes=5, seconds=30), now, translate=translate_en) == "5m 30s"

    def test_format_duration__when_exact_minutes__should_show_zero_seconds(self):
        now = datetime.now(UTC)
        assert _format_duration(now - timedelta(minutes=10), now, translate=translate_en) == "10m 0s"

    def test_format_duration__when_over_an_hour__should_show_hours_and_minutes(self):
        now = datetime.now(UTC)
        started_at = now - timedelta(hours=1, minutes=12)
        assert _format_duration(started_at, now, translate=translate_en) == "1h 12m"
        assert _format_duration(started_at, now, translate=functools.partial(_TRANSLATOR.translate, Locale.RU)) == (
            "1 ч 12 мин"
        )


def _make_standing(
    name: str,
    seat: int,
    score: int | None = None,
    final_score: int | None = None,
    user_id: str = "",
) -> PlayedGameStanding:
    return PlayedGameStanding(name=name, seat=seat, user_id=user_id, score=score, final_score=final_score)


class TestPrepareGamesForDisplay:
    def test_prepare_history_for_display__when_game_completed__should_mark_winner_viewer_and_labels(self):
        now = datetime.now(UTC)
        game = PlayedGame(
            game_id="game-1",
            started_at=now - timedelta(minutes=30),
            ended_at=now,
            end_reason="completed",
            game_type="hanchan",
            num_rounds_played=8,
            standings=[
                _make_standing(name="Alice", seat=2, score=35000, final_score=30),
                _make_standing(name="Bob", seat=0, score=25000, final_score=0, user_id=_VIEWER_USER_ID),
                _make_standing(name="Charlie", seat=1, score=22000, final_score=-10),
                _make_standing(name="Diana", seat=3, score=18000, final_score=-20),
            ],
        )
        result = _prepare_history_for_display([game], user_id=_VIEWER_USER_ID, translate=translate_en)
        assert len(result) == 1
        entry = result[0]
        assert entry["players"][0]["is_winner"] is True
        assert entry["players"][0]["name"] == "Alice"
        assert entry["players"][0]["score"] == 35000
        assert entry["players"][1]["score"] == 25000
        assert entry["players"][1]["is_winner"] is False
        assert (entry["game_type"].wind, entry["game_type"].name) == ("南", "Hanchan")
        assert entry["duration_label"] == "30m 0s"
        assert [player["is_viewer"] for player in entry["players"]] == [False, True, False, False]
        assert entry["viewer_replay_url"] == "/play/history/game-1?seat=0"
        assert entry["replay_url"] == "/play/history/game-1"

    def test_prepare_history_for_display__when_viewer_did_not_play__should_link_without_seat(self):
        game = PlayedGame(
            game_id="game-1",
            started_at=datetime.now(UTC),
            standings=[
                _make_standing(name="Alice", seat=2, user_id="alice-user-id"),
                _make_standing(name="Bob", seat=0, user_id=_VIEWER_USER_ID),
            ],
        )

        [entry] = _prepare_history_for_display([game], user_id="onlooker-user-id", translate=translate_en)
        assert [player["is_viewer"] for player in entry["players"]] == [False, False]
        assert entry["viewer_replay_url"] == "/play/history/game-1"

    def test_prepare_history_for_display__when_tonpusen__should_label_east_tonpuu(self):
        now = datetime.now(UTC)
        game = PlayedGame(game_id="g", started_at=now, game_type="tonpusen")

        result = _prepare_history_for_display([game], user_id=_VIEWER_USER_ID, translate=translate_en)
        assert (result[0]["game_type"].wind, result[0]["game_type"].name) == ("東", "Tonpuu")

    def test_prepare_history_for_display__when_game_type_unknown__should_have_no_label(self):
        now = datetime.now(UTC)
        game = PlayedGame(game_id="g", started_at=now, game_type="")

        result = _prepare_history_for_display([game], user_id=_VIEWER_USER_ID, translate=translate_en)
        assert result[0]["game_type"] is None

    def test_prepare_history_for_display__when_game_under_a_minute__should_show_seconds(self):
        now = datetime.now(UTC)
        game = PlayedGame(
            game_id="g",
            started_at=now - timedelta(seconds=30),
            ended_at=now,
            end_reason="completed",
        )
        result = _prepare_history_for_display([game], user_id=_VIEWER_USER_ID, translate=translate_en)
        assert result[0]["duration_label"] == "30s"

    def test_prepare_history_for_display__when_standings_empty__should_have_no_players(self):
        now = datetime.now(UTC)
        game = PlayedGame(game_id="g", started_at=now, standings=[])

        result = _prepare_history_for_display([game], user_id=_VIEWER_USER_ID, translate=translate_en)
        assert result[0]["players"] == []
