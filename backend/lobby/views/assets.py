"""Vite manifest utilities and Jinja2 template factory."""

from __future__ import annotations

import json
from pathlib import Path

from starlette.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def create_templates() -> Jinja2Templates:
    """Create Jinja2 template engine for lobby HTML templates."""
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def load_vite_manifest(game_assets_dir: str) -> dict[str, dict]:
    """Load the Vite manifest mapping source paths to build outputs.

    Vite 6.x stores the manifest at <outDir>/.vite/manifest.json.
    """
    manifest_path = Path(game_assets_dir).resolve() / ".vite" / "manifest.json"
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
    """Extract CSS URL from a Vite manifest entry.

    Vite extracts CSS into the `css` array when building from a JS entry point
    that imports SCSS/CSS files.
    """
    css_files = entry.get("css", [])
    if css_files:
        return f"{base_path}/{css_files[0]}"
    return None


def resolve_vite_asset_urls(manifest: dict[str, dict], base_path: str = "/game-assets") -> dict[str, str]:
    """Extract asset URLs from Vite manifest entries.

    Two entry points:
    - src/index.ts -> game_js + game_css
    - src/lobby/index.ts -> lobby_js + lobby_css

    Return a flat dict with keys: game_js, game_css, lobby_js, lobby_css.
    All dict access uses .get() to gracefully handle partial manifests.
    """
    base_path = base_path.rstrip("/")
    urls: dict[str, str] = {}

    game_entry = manifest.get("src/index.ts", {})
    game_js = game_entry.get("file")
    if game_js:
        urls["game_js"] = f"{base_path}/{game_js}"
    game_css = _resolve_css_url(game_entry, base_path)
    if game_css:
        urls["game_css"] = game_css

    lobby_entry = manifest.get("src/lobby/index.ts", {})
    lobby_js = lobby_entry.get("file")
    if lobby_js:
        urls["lobby_js"] = f"{base_path}/{lobby_js}"
    lobby_css = _resolve_css_url(lobby_entry, base_path)
    if lobby_css:
        urls["lobby_css"] = lobby_css

    return urls
