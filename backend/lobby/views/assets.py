from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.templating import Jinja2Templates

from lobby.auth.csrf import get_or_create_csrf_token, set_csrf_cookie

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from shared.auth.settings import AuthSettings

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
LOBBY_ENTRY = "src/index.ts"


def create_templates() -> Jinja2Templates:
    """
    Create Jinja2 template engine for lobby HTML templates.
    """
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def render_page(request: Request, *, template_name: str, context: dict[str, object]) -> Response:
    """
    Render a lobby page with the CSRF token its forms carry, setting the CSRF cookie when the token is new.
    """
    templates: Jinja2Templates = request.app.state.templates
    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(request, template_name, {**context, "csrf_token": csrf_token})
    if is_new:
        auth_settings: AuthSettings = request.app.state.auth_settings
        set_csrf_cookie(response, token=csrf_token, cookie_secure=auth_settings.cookie_secure)

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
