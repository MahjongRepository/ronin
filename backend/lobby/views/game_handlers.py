from __future__ import annotations

from typing import TYPE_CHECKING

from lobby.auth.csrf import get_or_create_csrf_token, set_csrf_cookie

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.templating import Jinja2Templates

    from lobby.views.game_client import GameClient


async def play_page(request: Request) -> Response:
    """
    GET /play/* — serve the game client's page; the game client routes the path itself.
    """
    game_client: GameClient = request.app.state.game_client
    return await game_client.serve_page()


async def storybook_page(request: Request) -> Response:
    """
    Render the lobby storybook page for development.
    """
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
        set_csrf_cookie(response, token=csrf_token, cookie_secure=auth_settings.cookie_secure)

    return response
