import pytest
from pydantic import ValidationError

from lobby.settings import LobbyServerSettings


class TestLobbyServerSettings:
    def test_lobby_server_settings__when_deployment_values_unset__should_raise_for_each(self, monkeypatch):
        for name in (
            "LOBBY_ALLOWED_HOSTS",
            "LOBBY_GAME_SERVER_URL",
            "LOBBY_GAME_SERVER_WS_URL",
            "LOBBY_REPLAY_DIR",
            "LOBBY_WS_ALLOWED_ORIGIN",
        ):
            monkeypatch.delenv(name)

        with pytest.raises(ValidationError) as exc_info:
            LobbyServerSettings()

        missing = {error["loc"][0] for error in exc_info.value.errors() if error["type"] == "missing"}
        assert missing == {"allowed_hosts", "game_server_url", "game_server_ws_url", "replay_dir", "ws_allowed_origin"}

    @pytest.mark.parametrize(
        ("env_name", "value"),
        [
            ("LOBBY_GAME_SERVER_URL", "ws://game:8711"),
            ("LOBBY_GAME_SERVER_WS_URL", "https://ronin.example"),
            ("LOBBY_GAME_SERVER_URL", "game:8711"),
            ("LOBBY_GAME_SERVER_URL", "http://"),
            ("LOBBY_GAME_SERVER_URL", "http://game:8711/api"),
            ("LOBBY_GAME_SERVER_WS_URL", "wss://ronin.example/ws"),
            ("LOBBY_GAME_SERVER_WS_URL", "wss://ronin.example?a=1"),
            ("LOBBY_GAME_SERVER_URL", "http://user:secret@game:8711"),
            ("LOBBY_GAME_SERVER_URL", "http://ga me:8711"),
            ("LOBBY_GAME_SERVER_URL", "http://game:not-a-port"),
            ("LOBBY_GAME_SERVER_URL", "http://game:65536"),
            ("LOBBY_GAME_SERVER_WS_URL", "wss://ronin.example:bad"),
            ("LOBBY_GAME_SERVER_WS_URL", "wss://ronin.example:65536"),
        ],
    )
    def test_lobby_server_settings__when_game_server_url_malformed__should_raise(self, monkeypatch, env_name, value):
        monkeypatch.setenv(env_name, value)
        with pytest.raises(ValidationError, match=env_name.removeprefix("LOBBY_").lower()):
            LobbyServerSettings()

    def test_lobby_server_settings__when_game_server_urls_have_trailing_slash__should_strip_it(self, monkeypatch):
        monkeypatch.setenv("LOBBY_GAME_SERVER_URL", "http://game:8711/")
        monkeypatch.setenv("LOBBY_GAME_SERVER_WS_URL", "wss://ronin.example/")
        settings = LobbyServerSettings()
        assert (settings.game_server_url, settings.game_server_ws_url) == ("http://game:8711", "wss://ronin.example")

    def test_lobby_server_settings__when_game_client_dev_url_not_an_origin__should_raise(self, monkeypatch):
        monkeypatch.setenv("LOBBY_GAME_CLIENT_DEV_URL", "http://localhost:5174/game-assets")
        with pytest.raises(ValidationError, match="game_client_dev_url"):
            LobbyServerSettings()

    def test_lobby_server_settings__when_log_dir_env_set__should_override_log_dir(self, monkeypatch):
        monkeypatch.setenv("LOBBY_LOG_DIR", "custom/lobby-logs")
        settings = LobbyServerSettings()
        assert settings.log_dir == "custom/lobby-logs"

    def test_lobby_server_settings__when_cors_origins_json_array__should_parse_list(self, monkeypatch):
        monkeypatch.setenv("LOBBY_CORS_ORIGINS", '["http://x.com","http://y.com"]')
        settings = LobbyServerSettings()
        assert settings.cors_origins == ["http://x.com", "http://y.com"]

    def test_lobby_server_settings__when_cors_origins_csv__should_parse_list(self, monkeypatch):
        monkeypatch.setenv("LOBBY_CORS_ORIGINS", "http://x.com,http://y.com")
        settings = LobbyServerSettings()
        assert settings.cors_origins == ["http://x.com", "http://y.com"]

    def test_lobby_server_settings__when_cors_origins_empty__should_raise_validation_error(self, monkeypatch):
        monkeypatch.setenv("LOBBY_CORS_ORIGINS", "")
        with pytest.raises(ValidationError, match="cors_origins"):
            LobbyServerSettings()

    def test_lobby_server_settings__when_vite_dev_url_unset__should_be_empty(self, monkeypatch):
        monkeypatch.delenv("LOBBY_VITE_DEV_URL", raising=False)
        settings = LobbyServerSettings()
        assert settings.vite_dev_url == ""

    def test_lobby_server_settings__when_vite_dev_url_env_set__should_override_vite_dev_url(self, monkeypatch):
        monkeypatch.setenv("LOBBY_VITE_DEV_URL", "http://localhost:5173")
        settings = LobbyServerSettings()
        assert settings.vite_dev_url == "http://localhost:5173"
