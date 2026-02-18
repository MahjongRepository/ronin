"""Auth settings shared between lobby and game server."""

from pydantic import Field
from pydantic_settings import BaseSettings


class AuthSettings(BaseSettings):
    model_config = {"env_prefix": "AUTH_"}

    # HMAC secret shared between lobby and game server -- required, no default.
    # The application fails to start if AUTH_GAME_TICKET_SECRET is not set.
    game_ticket_secret: str = Field(min_length=1)

    # User data file path
    users_file: str = "data/users.json"

    # Cookie Secure flag -- True in production, False for local dev (HTTP)
    cookie_secure: bool = False
