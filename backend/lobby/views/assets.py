from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from starlette.templating import Jinja2Templates

from lobby.auth.csrf import get_or_create_csrf_token, is_cross_site_post, set_csrf_cookie
from lobby.i18n import LANGUAGE_NAMES, format_number, resolve_request_locale

if TYPE_CHECKING:
    from collections.abc import Mapping

    from markupsafe import Markup
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.i18n import Translator
    from shared.auth.settings import AuthSettings

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
LOBBY_ENTRY = "src/index.ts"


def _i18n_context(request: Request) -> dict[str, object]:
    """
    Give every template the request's ``locale``, ``t(key, **params)``, which returns the message as escaped HTML,
    ``format_number(n)`` in the locale's digit grouping, and what the language switch needs: the languages by their
    native names and the page to return to (path and query).
    """
    translator: Translator = request.app.state.translator
    locale = resolve_request_locale(request).locale

    def t(key: str, /, **params: object) -> Markup:
        return translator.translate_markup(locale, key, **params)

    def format_locale_number(number: int) -> str:
        return format_number(locale, number)

    return {
        "locale": locale,
        "t": t,
        "format_number": format_locale_number,
        "language_names": LANGUAGE_NAMES,
        "current_page": _return_page(request),
    }


def _return_page(request: Request) -> str:
    """
    Return the page the language switch sends the user back to: this one for a GET, else the page that posted the form.

    A page rendered for a POST (a refused form, an error) has no GET route at its path, so returning there would fail;
    the same-origin page that sent the form, or the lobby, is the closest page to reopen.
    """
    if request.method in {"GET", "HEAD"}:
        query = request.url.query
        return f"{request.url.path}?{query}" if query else request.url.path

    return same_origin_referer_path(request) or "/"


def translate_for_request(request: Request, key: str, /, **params: object) -> str:
    """
    Return the message ``key`` as plain text in the request's locale, for a handler to pass to its template.
    """
    translator: Translator = request.app.state.translator
    return translator.translate(resolve_request_locale(request).locale, key, **params)


def create_templates() -> Jinja2Templates:
    """
    Create Jinja2 template engine for lobby HTML templates.
    """
    return Jinja2Templates(directory=str(TEMPLATES_DIR), context_processors=[_i18n_context])


def render_page(
    request: Request,
    *,
    template_name: str,
    context: dict[str, object],
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> Response:
    """
    Render a lobby page with the CSRF token its forms carry, setting the CSRF cookie when the token is new.

    An existing cookie is never replaced. A POST from another site arrives without it, so its answer sets none either. A
    page varies with the ``lang`` cookie, and one whose locale the browser's preference chose with that preference too.
    """
    templates: Jinja2Templates = request.app.state.templates
    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(
        request, template_name, {**context, "csrf_token": csrf_token}, status_code=status_code, headers=headers
    )
    if is_new and not is_cross_site_post(request):
        auth_settings: AuthSettings = request.app.state.auth_settings
        set_csrf_cookie(response, token=csrf_token, cookie_secure=auth_settings.cookie_secure)

    response.headers.add_vary_header("Cookie")
    if not resolve_request_locale(request).from_cookie:
        response.headers.add_vary_header("Accept-Language")

    return response


def load_vite_manifest(assets_dir: str) -> dict[str, dict]:
    """
    Load the Vite manifest mapping source paths to build outputs.

    Vite 6.x stores the manifest at <outDir>/.vite/manifest.json.
    """
    manifest_path = Path(assets_dir).resolve() / ".vite" / "manifest.json"
    if not manifest_path.exists():
        return {}

    try:
        data = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        msg = f"Malformed manifest.json at {manifest_path}: {e}"
        raise ValueError(msg) from e

    if not isinstance(data, dict):
        msg = f"manifest.json must be a JSON object, got {type(data).__name__}"
        raise TypeError(msg)

    return data


def _resolve_css_url(entry: dict, base_path: str) -> str | None:
    """
    Extract CSS URL from a Vite manifest entry.

    Vite extracts CSS into the `css` array when building from a JS entry point that imports SCSS/CSS files.
    """
    css_files = entry.get("css", [])
    if css_files:
        return f"{base_path}/{css_files[0]}"

    return None


def resolve_vite_asset_urls(manifest: dict[str, dict], base_path: str = "/lobby-assets") -> dict[str, str]:
    """
    Extract the lobby entry's script and stylesheet URLs from the Vite manifest.

    Return a dict with the keys ``lobby_js`` and ``lobby_css``, each present only when the manifest names it.
    """
    base_path = base_path.rstrip("/")
    urls: dict[str, str] = {}

    entry = manifest.get(LOBBY_ENTRY, {})
    lobby_js = entry.get("file")
    if lobby_js:
        urls["lobby_js"] = f"{base_path}/{lobby_js}"

    lobby_css = _resolve_css_url(entry, base_path)
    if lobby_css:
        urls["lobby_css"] = lobby_css

    return urls


def same_origin_referer_path(request: Request) -> str | None:
    """
    Return the path and query of the page that posted the form, or None when it is missing, malformed or off-site.

    Leading slashes and backslashes collapse to one slash: a browser reads ``//host/x`` and ``/\\host/x`` alike as a
    link to another host.
    """
    referer = request.headers.get("referer")
    if not referer:
        return None

    try:
        parsed = urlsplit(referer)
    except ValueError:
        return None

    if parsed.scheme not in {"http", "https"} or parsed.netloc != request.url.netloc:
        return None

    path = "/" + parsed.path.lstrip("/\\")
    return f"{path}?{parsed.query}" if parsed.query else path
