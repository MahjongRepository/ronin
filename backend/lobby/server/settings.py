"""Lobby server configuration via environment variables."""

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import field_validator
from pydantic_settings import BaseSettings

from shared.validators import StringListEnvSettingsSource, parse_string_list

if TYPE_CHECKING:
    from pydantic_settings.sources.base import PydanticBaseSettingsSource


class LobbyServerSettings(BaseSettings):
    model_config = {"env_prefix": "LOBBY_"}

    log_dir: str = "backend/logs/lobby"
    cors_origins: list[str] = []
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver", "*.local"]
    config_path: Path | None = None
    static_dir: str = "frontend/public"
    game_client_url: str = "/play"
    game_assets_dir: str = "frontend/dist"
    vite_dev_url: str = ""  # Set to "http://localhost:5173" via LOBBY_VITE_DEV_URL when running Vite dev server
    ws_allowed_origin: str | None = "http://localhost:8710"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def validate_cors_origins(cls, v: str | list[str]) -> list[str]:
        return parse_string_list(v, allow_empty=True)

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def validate_allowed_hosts(cls, v: str | list[str]) -> list[str]:
        return parse_string_list(v)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, StringListEnvSettingsSource(settings_cls), dotenv_settings, file_secret_settings)
