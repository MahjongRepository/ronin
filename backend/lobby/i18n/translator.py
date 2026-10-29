from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeIs

import structlog
from markupsafe import Markup, escape

from lobby.i18n.catalog import PLACEHOLDER, PLURAL_PARAM, placeholders
from lobby.i18n.locale import DEFAULT_LOCALE, Locale

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from lobby.i18n.catalog import Catalogs

logger = structlog.get_logger()

_NARROW_NO_BREAK_SPACE = "\N{NARROW NO-BREAK SPACE}"
_RU_FEW_LAST_DIGITS = range(2, 5)
_RU_TEENS = range(11, 15)


class I18nError(Exception):
    """
    A lookup the catalog cannot answer as asked: a missing key or translation, a param mismatch, or a wrong plural call.
    """

    def __init__(self, key: str, reason: str) -> None:
        super().__init__(f"{key}: {reason}")
        self.key = key
        self.reason = reason


def plural_category(locale: Locale, count: int) -> str:
    """
    Return the CLDR cardinal category of ``count`` in ``locale``: one/other in en, other in ja, one/few/many in ru.
    """
    if locale == Locale.JA:
        return "other"

    if locale == Locale.EN:
        return "one" if count == 1 else "other"

    last_digit, last_two_digits = abs(count) % 10, abs(count) % 100
    if last_digit == 1 and last_two_digits != 11:  # noqa: PLR2004 - the CLDR rule's own numbers
        return "one"

    if last_digit in _RU_FEW_LAST_DIGITS and last_two_digits not in _RU_TEENS:
        return "few"

    return "many"


def format_number(locale: Locale, number: int) -> str:
    """
    Format an integer with the locale's digit grouping: commas in en and ja, a narrow no-break space in ru.
    """
    grouped = f"{number:,}"
    return grouped.replace(",", _NARROW_NO_BREAK_SPACE) if locale == Locale.RU else grouped


def _is_number(value: object) -> TypeIs[int]:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class Translator:
    """
    Look messages up in the loaded catalogs.

    Strict, a lookup error raises; otherwise it renders the en message and logs one warning per distinct key.
    """

    catalogs: Catalogs
    strict: bool
    _reported_keys: set[str] = field(default_factory=set, compare=False, repr=False)

    def translate(self, locale: Locale, key: str, /, **params: object) -> str:
        """
        Return the message ``key`` in ``locale`` as plain text, with ``params`` filled in.
        """
        return self._render(locale, key, params, convert=str)

    def translate_markup(self, locale: Locale, key: str, /, **params: object) -> Markup:
        """
        Return the message ``key`` as HTML: the text and every ``str`` param escaped, a ``Markup`` param kept as is.
        """
        return Markup(self._render(locale, key, params, convert=escape))  # noqa: S704 - every piece is escaped

    def _render(
        self, locale: Locale, key: str, params: Mapping[str, object], *, convert: Callable[[object], str]
    ) -> str:
        try:
            return self._format(locale, key, params, convert=convert)
        except I18nError as e:
            if self.strict:
                raise

            self._report(locale, e)
            return self._render_fallback(key, params, convert=convert)

    def _format(
        self, locale: Locale, key: str, params: Mapping[str, object], *, convert: Callable[[object], str]
    ) -> str:
        """
        Fill in the message, raising ``I18nError`` when the call does not match the en message's params or plurality.
        """
        source = self.catalogs[DEFAULT_LOCALE].get(key)
        if source is None:
            raise I18nError(key, "missing key")

        expected = placeholders(source)
        missing, extra = expected - params.keys(), params.keys() - expected
        if isinstance(source, str) and PLURAL_PARAM in params:
            raise I18nError(key, "not a plural key")

        if missing:
            raise I18nError(key, f"missing params {sorted(missing)}")

        if extra:
            raise I18nError(key, f"unexpected params {sorted(extra)}")

        message = self.catalogs[locale].get(key)
        if message is None:
            raise I18nError(key, f"missing {locale.value} translation")

        if isinstance(message, str):
            return _substitute(message, params, locale=locale, convert=convert)

        count = params[PLURAL_PARAM]
        if not _is_number(count):
            raise I18nError(key, "plural count is not an integer")

        return _substitute(message[plural_category(locale, count)], params, locale=locale, convert=convert)

    def _render_fallback(self, key: str, params: Mapping[str, object], *, convert: Callable[[object], str]) -> str:
        """
        Render the en message with whatever params fit it, or the key itself when en lacks it.
        """
        source = self.catalogs[DEFAULT_LOCALE].get(key)
        if source is None:
            return convert(key)

        if isinstance(source, str):
            return _substitute(source, params, locale=DEFAULT_LOCALE, convert=convert)

        count = params.get(PLURAL_PARAM)
        category = plural_category(DEFAULT_LOCALE, count) if isinstance(count, int) else "other"
        return _substitute(source[category], params, locale=DEFAULT_LOCALE, convert=convert)

    def _report(self, locale: Locale, error: I18nError) -> None:
        if error.key in self._reported_keys:
            return

        self._reported_keys.add(error.key)
        logger.warning("i18n error", key=error.key, locale=locale.value, reason=error.reason)


def _substitute(text: str, params: Mapping[str, object], *, locale: Locale, convert: Callable[[object], str]) -> str:
    """
    Convert the message's literal text and fill each placeholder; an integer param gets the locale's number format.

    A placeholder without a param stays as written: only the production fallback renders one.
    """
    pieces = PLACEHOLDER.split(text)
    rendered = []
    for index, piece in enumerate(pieces):
        is_placeholder = index % 2 == 1
        if not is_placeholder:
            rendered.append(convert(piece))
        elif piece not in params:
            rendered.append(convert(f"{{{piece}}}"))
        else:
            value = params[piece]
            rendered.append(convert(format_number(locale, value) if _is_number(value) else value))

    return "".join(rendered)
