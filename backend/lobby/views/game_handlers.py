"""Game client and development page handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import PlainTextResponse

from lobby.server.csrf import get_or_create_csrf_token, set_csrf_cookie

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.templating import Jinja2Templates


async def play_page(request: Request) -> Response:
    """GET /play/{game_id} — render the game client page."""
    templates: Jinja2Templates = request.app.state.templates
    if not request.app.state.game_assets_available:
        return PlainTextResponse("Game client assets not available", status_code=503)
    return templates.TemplateResponse(request, "play.html")


async def storybook_page(request: Request) -> Response:
    """Render the lobby storybook page for development."""
    templates: Jinja2Templates = request.app.state.templates
    username = request.user.username if request.user.is_authenticated else None
    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "storybook.html",
        {"username": username, "csrf_token": csrf_token},
    )
    if is_new:
        auth_settings = request.app.state.auth_settings
        set_csrf_cookie(response, csrf_token, cookie_secure=auth_settings.cookie_secure)
    return response
