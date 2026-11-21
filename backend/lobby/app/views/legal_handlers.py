from __future__ import annotations

from typing import TYPE_CHECKING

from app.i18n import resolve_request_locale
from app.views.assets import render_page

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


async def terms_page(request: Request) -> Response:
    """GET /terms - render the terms of service in the request's language."""
    return _render_legal_page(request, document="terms")


async def privacy_page(request: Request) -> Response:
    """GET /privacy - render the privacy policy in the request's language."""
    return _render_legal_page(request, document="privacy")


def _render_legal_page(request: Request, *, document: str) -> Response:
    """
    Render one legal document from its per-language template.

    Each language has its own whole template rather than catalog keys: the text is a long legal prose, edited per
    language as one piece.
    """
    locale = resolve_request_locale(request).locale
    return render_page(request, template_name=f"legal/{document}.{locale}.html", context={})
