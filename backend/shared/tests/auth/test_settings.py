import pytest
from pydantic import ValidationError

from shared.auth.settings import AuthSettings


class TestAuthSettings:
    def test_auth_settings__when_env_set__should_read_game_ticket_secret(self, monkeypatch):
        monkeypatch.setenv("AUTH_GAME_TICKET_SECRET", "my-secret")
        settings = AuthSettings()
        assert settings.game_ticket_secret == "my-secret"

    def test_auth_settings__when_game_ticket_secret_missing__should_raise(self, monkeypatch):
        monkeypatch.delenv("AUTH_GAME_TICKET_SECRET", raising=False)
        with pytest.raises(ValidationError, match="game_ticket_secret"):
            AuthSettings()
