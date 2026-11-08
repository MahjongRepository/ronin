from __future__ import annotations

from typing import TYPE_CHECKING

from lobby.i18n import resolve_request_locale
from lobby.views.assets import render_page

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
    Render one legal document from its per-language template, with the navigation of the user signed in, if any.

    Each language has its own whole template rather than catalog keys: the text is a long legal prose, edited per
    language as one piece.
    """
    locale = resolve_request_locale(request).locale
    user = request.scope.get("user")
    return render_page(
        request,
        template_name=f"legal/{document}.{locale}.html",
        context={"username": user.username if user is not None and user.is_authenticated else None},
    )
