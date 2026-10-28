from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse

from lobby.i18n import parse_locale, set_lang_cookie
from lobby.views.auth_handlers import parse_next_path
from lobby.views.error_pages import validate_csrf

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from shared.auth.settings import AuthSettings


async def set_language(request: Request) -> Response:
    """
    POST /lang - store the chosen language in the ``lang`` cookie and return to the page the choice was made on.
    """
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    locale = parse_locale(form.get("lang"))
    if locale is None:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="Unsupported language")

    auth_settings: AuthSettings = request.app.state.auth_settings
    response = RedirectResponse(parse_next_path(form.get("next")) or "/", status_code=HTTPStatus.SEE_OTHER)
    set_lang_cookie(response, locale=locale, cookie_secure=auth_settings.cookie_secure)
    return response
