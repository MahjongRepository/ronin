from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

LANG_COOKIE_NAME = "lang"
LANG_COOKIE_MAX_AGE_SECONDS = 365 * 24 * 60 * 60


class Locale(StrEnum):
    EN = "en"
    JA = "ja"
    RU = "ru"


DEFAULT_LOCALE = Locale.EN

LANGUAGE_NAMES = {
    Locale.EN: "English",
    Locale.JA: "日本語",
    Locale.RU: "Русский",
}


@dataclass(frozen=True)
class ResolvedLocale:
    """
    The page's locale and whether it came from the ``lang`` cookie (otherwise it came from the browser's preference).
    """

    locale: Locale
    from_cookie: bool


def parse_locale(value: object) -> Locale | None:
    """
    Return the supported locale ``value`` names exactly, or None for anything else.
    """
    if not isinstance(value, str):
        return None

    try:
        return Locale(value)
    except ValueError:
        return None


def _parse_quality(params: list[str]) -> float | None:
    """
    Return an ``Accept-Language`` entry's q-value (1 when absent), or None when it is malformed.
    """
    for param in params:
        name, _, value = param.strip().partition("=")
        if name.strip().lower() != "q":
            continue

        try:
            return float(value)
        except ValueError:
            return None

    return 1.0


def _preferred_locales(accept_language: str) -> list[Locale]:
    """
    Return the supported locales an ``Accept-Language`` header asks for, by q-value and then header order.

    Each entry is matched by its primary subtag, case-insensitive; ``*``, malformed entries and q=0 are ignored.
    """
    ranked: list[tuple[float, int, Locale]] = []
    for position, entry in enumerate(accept_language.split(",")):
        tag, *params = entry.split(";")
        locale = parse_locale(tag.strip().split("-")[0].lower())
        quality = _parse_quality(params)
        if locale is None or quality is None or quality <= 0:
            continue

        ranked.append((-quality, position, locale))

    return [locale for _, _, locale in sorted(ranked)]


def resolve_locale(*, cookie: str | None, accept_language: str | None) -> ResolvedLocale:
    """
    Pick the locale: a valid ``lang`` cookie, else the first supported browser preference, else English.
    """
    from_cookie = parse_locale(cookie)
    if from_cookie is not None:
        return ResolvedLocale(locale=from_cookie, from_cookie=True)

    preferred = _preferred_locales(accept_language or "")
    return ResolvedLocale(locale=preferred[0] if preferred else DEFAULT_LOCALE, from_cookie=False)


def resolve_request_locale(request: Request) -> ResolvedLocale:
    """
    Resolve the request's locale once and keep it on ``request.state`` for every later reader of the same request.
    """
    resolved = getattr(request.state, "resolved_locale", None)
    if isinstance(resolved, ResolvedLocale):
        return resolved

    resolved = resolve_locale(
        cookie=request.cookies.get(LANG_COOKIE_NAME),
        accept_language=request.headers.get("accept-language"),
    )
    request.state.resolved_locale = resolved
    return resolved


def set_lang_cookie(response: Response, *, locale: Locale, cookie_secure: bool) -> None:
    """
    Set the ``lang`` cookie the lobby and the game client both read; not HttpOnly, since the game client reads it.
    """
    response.set_cookie(
        key=LANG_COOKIE_NAME,
        value=locale.value,
        max_age=LANG_COOKIE_MAX_AGE_SECONDS,
        path="/",
        samesite="lax",
        secure=cookie_secure,
        httponly=False,
    )
