from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from app.auth.csrf import is_csrf_valid
from app.views.error_pages import NO_STORE_HEADERS, json_csrf_rejection
from app.views.json_body import parse_json_body

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from app.auth.service import AuthService
    from app.dal.models import Player

API_KEY_HEADER = "X-API-Key"


async def find_account(request: Request) -> Player | None:
    """
    Return the account of the authenticated user, or None for a guest, who has no account.
    """
    auth_service: AuthService = request.app.state.auth_service
    return await auth_service.get_account(user_id=request.user.user_id, username=request.user.username)


async def lobby_api_token(request: Request) -> JSONResponse:
    """
    GET /api/lobby/api-token - whether the user can hold an API token and already holds one, never the token itself.
    """
    account = await find_account(request)
    return JSONResponse(
        {
            "has_account": account is not None,
            "has_token": account is not None and account.api_key_hash is not None,
            "header": API_KEY_HEADER,
        },
        headers=NO_STORE_HEADERS,
    )


async def lobby_issue_api_token(request: Request) -> Response:
    """
    POST /api/lobby/api-token - issue or rotate the account's API token and answer it once, uncached.

    A guest has no account to hold a token and gets a 403 ``guest_account``.
    """
    if await parse_json_body(request) is None:
        return JSONResponse({"error": "invalid_body"}, status_code=HTTPStatus.BAD_REQUEST, headers=NO_STORE_HEADERS)

    if not is_csrf_valid(request):
        return json_csrf_rejection(request)

    account = await find_account(request)
    if account is None:
        return JSONResponse({"error": "guest_account"}, status_code=HTTPStatus.FORBIDDEN, headers=NO_STORE_HEADERS)

    auth_service: AuthService = request.app.state.auth_service
    raw_token = await auth_service.issue_account_api_key(account)
    return JSONResponse({"token": raw_token}, status_code=HTTPStatus.CREATED, headers=NO_STORE_HEADERS)
