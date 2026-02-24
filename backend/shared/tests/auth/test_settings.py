"""Tests for AuthSettings configuration."""

import pytest
from pydantic import ValidationError

from shared.auth.settings import AuthSettings


class TestAuthSettings:
    def test_reads_game_ticket_secret_from_env(self, monkeypatch):
        monkeypatch.setenv("AUTH_GAME_TICKET_SECRET", "my-secret")
        settings = AuthSettings()
        assert settings.game_ticket_secret == "my-secret"

    def test_missing_game_ticket_secret_raises(self, monkeypatch):
        monkeypatch.delenv("AUTH_GAME_TICKET_SECRET", raising=False)
        with pytest.raises(ValidationError, match="game_ticket_secret"):
            AuthSettings()

    def test_database_path_from_env(self, monkeypatch):
        monkeypatch.setenv("AUTH_GAME_TICKET_SECRET", "s")
        monkeypatch.setenv("AUTH_DATABASE_PATH", "custom/path/storage.db")
        settings = AuthSettings()
        assert settings.database_path == "custom/path/storage.db"

    def test_legacy_users_file_from_env(self, monkeypatch):
        monkeypatch.setenv("AUTH_GAME_TICKET_SECRET", "s")
        monkeypatch.setenv("AUTH_USERS_FILE", "custom/legacy.json")
        settings = AuthSettings()
        assert settings.legacy_users_file == "custom/legacy.json"
