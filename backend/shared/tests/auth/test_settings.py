import pytest
from pydantic import ValidationError

from shared.auth.settings import AuthSettings


class TestAuthSettings:
    def test_auth_settings__when_env_set__should_read_game_ticket_secret(self, monkeypatch):
        monkeypatch.setenv("AUTH_GAME_TICKET_SECRET", "my-secret")
        settings = AuthSettings()
        assert settings.game_ticket_secret == "my-secret"

    def test_auth_settings__when_deployment_values_unset__should_raise_for_each(self, monkeypatch):
        monkeypatch.delenv("AUTH_GAME_TICKET_SECRET")
        monkeypatch.delenv("AUTH_DATABASE_PATH")
        with pytest.raises(ValidationError) as exc_info:
            AuthSettings()

        missing = {error["loc"][0] for error in exc_info.value.errors() if error["type"] == "missing"}
        assert missing == {"game_ticket_secret", "database_path"}
