from __future__ import annotations

import secrets
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from starlette.datastructures import FormData
    from starlette.requests import Request
    from starlette.responses import Response

CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"


def get_or_create_csrf_token(request: Request) -> tuple[str, bool]:
    """
    Return the CSRF token from the cookie, or generate a new one.

    Returns (token, is_new) where is_new indicates a cookie must be set.
    """
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if token:
        return token, False

    return secrets.token_urlsafe(32), True


def is_cross_site_post(request: Request) -> bool:
    """
    Return whether the browser sent this request without the SameSite=Lax CSRF cookie: a POST from another site.

    Such a request looks like one from a browser that has no cookie yet, so a page answering it must not set a new one:
    that would overwrite the cookie the browser withheld and stale the forms of the user's other tabs. A browser without
    ``Sec-Fetch-Site`` is judged by ``Origin``; a malformed or ``null`` one counts as another site.
    """
    if request.method in {"GET", "HEAD"}:
        return False

    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site is not None:
        return fetch_site == "cross-site"

    origin = request.headers.get("origin")
    if origin is None:
        return False

    try:
        parts = urlsplit(origin)
    except ValueError:
        return True
    return (parts.scheme, parts.netloc) != (request.url.scheme, request.url.netloc)


def set_csrf_cookie(response: Response, *, token: str, cookie_secure: bool) -> None:
    """
    Set the CSRF token cookie on the response.
    """
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=cookie_secure,
        path="/",
    )


def is_csrf_valid(request: Request, form_data: FormData) -> bool:
    """
    Return whether the form's CSRF token is present and equals the cookie's.

    The tokens are compared as bytes: ``compare_digest`` raises on a str holding a non-ASCII character, which a
    crafted form token can carry.
    """
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    form_token = form_data.get(CSRF_FORM_FIELD)
    if not cookie_token or not form_token or not isinstance(form_token, str):
        return False

    return secrets.compare_digest(cookie_token.encode(), form_token.encode())
