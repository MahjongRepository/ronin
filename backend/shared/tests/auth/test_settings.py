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
