from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request


async def parse_json_body(request: Request) -> dict | None:
    try:
        body = await request.json()
    except ValueError, json.JSONDecodeError:
        return None

    if not isinstance(body, dict):
        return None

    return body
