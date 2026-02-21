"""Auth settings shared between lobby and game server."""

from pydantic import Field
from pydantic_settings import BaseSettings


class AuthSettings(BaseSettings):
    model_config = {"env_prefix": "AUTH_", "populate_by_name": True}

    # HMAC secret shared between lobby and game server -- required, no default.
    # The application fails to start if AUTH_GAME_TICKET_SECRET is not set.
    game_ticket_secret: str = Field(min_length=1)

    # SQLite database file path
    database_path: str = "backend/storage.db"

    # Legacy JSON users file for migration input
    legacy_users_file: str = Field(default="data/users.json", validation_alias="AUTH_USERS_FILE")

    # Cookie Secure flag -- True in production, False for local dev (HTTP)
    cookie_secure: bool = False
