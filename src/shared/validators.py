"""Shared validation helpers for service settings."""

import json
from typing import TYPE_CHECKING, Any

from pydantic_settings import EnvSettingsSource

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo


def parse_cors_origins(value: str | list[str]) -> list[str]:
    """Parse CORS origins from environment variable or config value.

    Accepts:
    - A list of strings (returned as-is)
    - A JSON array string: '["http://a","http://b"]'
    - A comma-separated string: 'http://a,http://b'

    Raises ValueError for malformed values.
    """
    if isinstance(value, list):
        return value

    stripped = value.strip()
    if not stripped:
        raise ValueError("CORS origins value must not be empty")

    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON array for CORS origins: {e}") from e
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("CORS origins JSON must be an array of strings")
        return parsed

    return [origin.strip() for origin in stripped.split(",") if origin.strip()]


class CorsEnvSettingsSource(EnvSettingsSource):
    """Env settings source that passes cors_origins as a raw string to field validators.

    pydantic-settings tries to JSON-decode list-typed fields from env vars before
    validators run. This subclass bypasses that for cors_origins so our custom
    parse_cors_origins validator handles both JSON and CSV formats.
    """

    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: Any,  # noqa: ANN401
        value_is_complex: bool,  # noqa: FBT001
    ) -> Any:  # noqa: ANN401
        if field_name == "cors_origins" and isinstance(value, str):
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)
