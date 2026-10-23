import json


def parse_string_list(value: str | list[str], *, allow_empty: bool = False) -> list[str]:
    """
    Parse a string list from environment variable or config value.

    Accepts:
    - A list of strings (returned as-is)
    - A JSON array string: '["a","b"]'
    - A comma-separated string: 'a,b'

    Raises ValueError for empty string values or malformed JSON.
    When allow_empty is False (default), also rejects empty lists.
    """
    if isinstance(value, list):
        if not allow_empty and not value:
            raise ValueError("String list value must not be empty")

        return value

    stripped = value.strip()
    if not stripped:
        raise ValueError("String list value must not be empty")

    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON array: {e}") from e

        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("JSON value must be an array of strings")

        if not allow_empty and not parsed:
            raise ValueError("String list value must not be empty")

        return parsed

    result = [origin.strip() for origin in stripped.split(",") if origin.strip()]
    if not allow_empty and not result:
        raise ValueError("String list value must not be empty")

    return result
