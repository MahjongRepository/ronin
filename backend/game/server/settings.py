"""Game server configuration via environment variables."""

from typing import TYPE_CHECKING

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from shared.validators import CorsEnvSettingsSource, parse_cors_origins

if TYPE_CHECKING:
    from pydantic_settings.sources.base import PydanticBaseSettingsSource


class GameServerSettings(BaseSettings):
    model_config = {"env_prefix": "GAME_"}

    max_capacity: int = Field(default=100, ge=1)
    log_dir: str = Field(default="backend/logs/game", min_length=1)
    cors_origins: list[str] = ["http://localhost:8712"]
    replay_dir: str = Field(default="backend/data/replays", min_length=1)
    room_ttl_seconds: int = Field(default=3600, ge=60)  # 1 hour default, min 60s

    # Read from AUTH_GAME_TICKET_SECRET (not GAME_GAME_TICKET_SECRET).
    # The secret lives under the AUTH_ namespace because it's shared auth infrastructure,
    # but GameServerSettings uses GAME_ prefix. validation_alias overrides the env var name.
    game_ticket_secret: str = Field(validation_alias="AUTH_GAME_TICKET_SECRET", min_length=1)

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
        return init_settings, CorsEnvSettingsSource(settings_cls), dotenv_settings, file_secret_settings
