from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import FileResponse, PlainTextResponse

from lobby.auth.csrf import get_or_create_csrf_token, set_csrf_cookie

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.templating import Jinja2Templates


async def play_page(request: Request) -> Response:
    """
    GET /play/{game_id} — render the game client page.
    """
    templates: Jinja2Templates = request.app.state.templates
    if not request.app.state.game_assets_available:
        return PlainTextResponse("Game client assets not available", status_code=503)

    return templates.TemplateResponse(request, "play.html")


async def play_ng_page(request: Request) -> Response:
    """GET /play-ng/{game_id} — serve the Majiang game client page (ronin.html).

    The page itself is static (built by Majiang's npm build); a <base> tag
    points all assets at the /majiang/ static mount. The game client reads
    game_id from the URL and the game ticket from sessionStorage.
    """
    if not request.app.state.majiang_available:
        return PlainTextResponse("Majiang client assets not available", status_code=503)
    page = request.app.state.majiang_dir / "ronin.html"
    if not page.is_file():
        return PlainTextResponse("Majiang client page not found (run npm build in Majiang)", status_code=503)
    return FileResponse(page)


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
