from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.exceptions import HTTPException

from lobby.views.assets import render_page
from lobby.views.error_pages import validate_csrf

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from shared.auth.service import AuthService
    from shared.dal.models import Player

API_KEY_HEADER = "X-API-Key"
_NO_STORE = {"Cache-Control": "no-store"}


async def _find_account(request: Request) -> Player | None:
    auth_service: AuthService = request.app.state.auth_service
    return await auth_service.get_account(user_id=request.user.user_id, username=request.user.username)


def _render_settings(
    request: Request,
    *,
    account: Player | None,
    issued_token: str | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    return render_page(
        request,
        template_name="settings.html",
        context={
            "username": request.user.username,
            "has_account": account is not None,
            "has_token": issued_token is not None or (account is not None and account.api_key_hash is not None),
            "issued_token": issued_token,
            "api_key_header": API_KEY_HEADER,
        },
        headers=headers,
    )


async def settings_page(request: Request) -> Response:
    """
    GET /settings - render the settings page; an account also sees its API token section, a guest does not.
    """
    return _render_settings(request, account=await _find_account(request))


async def issue_api_token(request: Request) -> Response:
    """
    POST /settings/api-token - issue or rotate the account's API token and show it once, uncached.

    A guest has no account to hold a token and gets a 403.
    """
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    account = await _find_account(request)
    if account is None:
        raise HTTPException(HTTPStatus.FORBIDDEN)

    auth_service: AuthService = request.app.state.auth_service
    raw_token = await auth_service.issue_account_api_key(account)
    return _render_settings(request, account=account, issued_token=raw_token, headers=_NO_STORE)
