from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from lobby.i18n.locale import DEFAULT_LOCALE, Locale

if TYPE_CHECKING:
    from collections.abc import Mapping

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
PLURAL_PARAM = "count"
PLURAL_CATEGORIES = {
    Locale.EN: frozenset({"one", "other"}),
    Locale.JA: frozenset({"other"}),
    Locale.RU: frozenset({"one", "few", "many", "other"}),
}

type Message = str | dict[str, str]
type Catalog = dict[str, Message]
type Catalogs = Mapping[Locale, Catalog]


class CatalogError(Exception):
    """
    A catalog file that the lobby must not start with: unreadable, malformed, or out of step with the en catalog.
    """


def placeholders(message: Message) -> frozenset[str]:
    """
    Return a message's placeholder names; a plural message's are those of all its categories.
    """
    texts = message.values() if isinstance(message, dict) else [message]
    return frozenset(name for text in texts for name in PLACEHOLDER.findall(text))


def _read_catalog(path: Path, locale: Locale) -> Catalog:
    """
    Read one locale's catalog, checking that every value is a string or a plural object of the locale's categories.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CatalogError(f"{path}: cannot read catalog: {e}") from e

    if not isinstance(data, dict):
        raise CatalogError(f"{path}: a catalog must be one JSON object")

    catalog: Catalog = {}
    for key, value in data.items():
        if isinstance(value, str):
            catalog[key] = value
            continue

        if not isinstance(value, dict) or set(value) != PLURAL_CATEGORIES[locale]:
            raise CatalogError(f"{path}: {key}: not a string or a plural of {sorted(PLURAL_CATEGORIES[locale])}")

        if not all(isinstance(text, str) for text in value.values()):
            raise CatalogError(f"{path}: {key}: plural forms must be strings")

        catalog[key] = value

    return catalog


def _check_against_source(locale: Locale, catalog: Catalog, source: Catalog) -> None:
    """
    Raise when a catalog's keys, plural shapes or placeholder sets differ from the en catalog's.
    """
    if catalog.keys() != source.keys():
        difference = sorted(catalog.keys() ^ source.keys())
        raise CatalogError(f"{locale}: keys differ from {DEFAULT_LOCALE}: {difference}")

    for key, message in catalog.items():
        if isinstance(message, dict) != isinstance(source[key], dict):
            raise CatalogError(f"{locale}: {key}: plural in one locale and not in the other")

        if placeholders(message) != placeholders(source[key]):
            raise CatalogError(f"{locale}: {key}: placeholders differ from {DEFAULT_LOCALE}")


def load_catalogs(directory: Path = LOCALES_DIR) -> Catalogs:
    """
    Load every locale's catalog from ``directory`` and check them against en, raising ``CatalogError`` on any problem.
    """
    catalogs = {locale: _read_catalog(directory / f"{locale}.json", locale) for locale in Locale}
    source = catalogs[DEFAULT_LOCALE]
    for locale, catalog in catalogs.items():
        _check_against_source(locale, catalog, source)

    return catalogs
