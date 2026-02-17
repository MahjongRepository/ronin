"""Lobby server configuration via environment variables."""

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import field_validator
from pydantic_settings import BaseSettings

from shared.validators import CorsEnvSettingsSource, parse_cors_origins

if TYPE_CHECKING:
    from pydantic_settings.sources.base import PydanticBaseSettingsSource


class LobbyServerSettings(BaseSettings):
    model_config = {"env_prefix": "LOBBY_"}

    log_dir: str = "backend/logs/lobby"
    cors_origins: list[str] = ["http://localhost:8712"]
    config_path: Path | None = None
    static_dir: str = "frontend/public"
    game_client_url: str = "http://localhost:8712"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def validate_cors_origins(cls, v: str | list[str]) -> list[str]:
        return parse_cors_origins(v)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, CorsEnvSettingsSource(settings_cls), dotenv_settings, file_secret_settings)
