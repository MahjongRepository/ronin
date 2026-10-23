from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode

from shared.validators import parse_string_list


class GameServerSettings(BaseSettings):
    model_config = {"env_prefix": "GAME_"}

    max_capacity: int = Field(default=100, ge=1)
    log_dir: str = ""
    cors_origins: Annotated[list[str], NoDecode]
    replay_dir: str = Field(min_length=1)

    # SQLite database file path shared with the lobby service.
    database_path: str = Field(validation_alias="AUTH_DATABASE_PATH")

    # Read from AUTH_GAME_TICKET_SECRET (not GAME_GAME_TICKET_SECRET).
    # The secret lives under the AUTH_ namespace because it's shared auth infrastructure,
    # but GameServerSettings uses GAME_ prefix. validation_alias overrides the env var name.
    game_ticket_secret: str = Field(validation_alias="AUTH_GAME_TICKET_SECRET", min_length=1)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def validate_cors_origins(cls, v: str | list[str]) -> list[str]:
        return parse_string_list(v)
