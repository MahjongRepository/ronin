from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode

from shared.validators import parse_string_list

_HTTP_SCHEMES = frozenset({"http", "https"})
_WS_SCHEMES = frozenset({"ws", "wss"})


def _parse_url_origin(value: str, schemes: frozenset[str]) -> str:
    """
    Validate that ``value`` is a bare origin (scheme, host, optional port) with one of ``schemes``.

    Return it as ``scheme://host[:port]`` with no trailing slash, so callers can append a path.
    """
    parts = urlsplit(value.strip())
    if parts.scheme not in schemes:
        raise ValueError(f"URL scheme must be one of {sorted(schemes)}: {value!r}")

    if not parts.hostname or any(char.isspace() for char in parts.netloc):
        raise ValueError(f"URL must name a host without whitespace: {value!r}")

    try:
        parts.port  # noqa: B018
    except ValueError as e:
        raise ValueError(f"URL port must be a number from 0 to 65535: {value!r}") from e

    if parts.username is not None or parts.password is not None:
        raise ValueError(f"URL must not carry credentials: {value!r}")

    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ValueError(f"URL must be an origin without a path, query or fragment: {value!r}")

    return f"{parts.scheme}://{parts.netloc}"


class LobbyServerSettings(BaseSettings):
    model_config = {"env_prefix": "LOBBY_"}

    log_dir: str = ""
    cors_origins: Annotated[list[str], NoDecode] = []
    allowed_hosts: Annotated[list[str], NoDecode]
    game_server_url: str
    game_server_ws_url: str
    static_dir: str = "frontend/lobby/public"
    assets_dir: str = "frontend/lobby/dist"
    vite_dev_url: str = ""  # Set to "http://localhost:5173" via LOBBY_VITE_DEV_URL when running Vite dev server
    game_client_url: str = "/play"
    game_client_dir: str = "frontend/game/dist"
    game_client_dev_url: str = ""
    replay_dir: str = Field(min_length=1)
    ws_allowed_origin: str = Field(min_length=1)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def validate_cors_origins(cls, v: str | list[str]) -> list[str]:
        return parse_string_list(v, allow_empty=True)

    @field_validator("game_server_url")
    @classmethod
    def validate_game_server_url(cls, v: str) -> str:
        return _parse_url_origin(v, _HTTP_SCHEMES)

    @field_validator("game_server_ws_url")
    @classmethod
    def validate_game_server_ws_url(cls, v: str) -> str:
        return _parse_url_origin(v, _WS_SCHEMES)

    @field_validator("game_client_dev_url")
    @classmethod
    def validate_game_client_dev_url(cls, v: str) -> str:
        if not v:
            return v

        return _parse_url_origin(v, _HTTP_SCHEMES)

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def validate_allowed_hosts(cls, v: str | list[str]) -> list[str]:
        return parse_string_list(v)
