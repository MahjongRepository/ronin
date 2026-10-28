"""
Check the i18n catalogs of every app against the rules of docs/i18n.md.

Each problem prints one line naming the file and the key; the exit status is 1 when there is any.
"""

from __future__ import annotations

import itertools
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LOCALES = ("en", "ja", "ru")
SOURCE_LOCALE = "en"
PLURAL_CATEGORIES = {
    "en": frozenset({"one", "other"}),
    "ja": frozenset({"other"}),
    "ru": frozenset({"one", "few", "many", "other"}),
}
PLURAL_PARAM = "count"

PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
HTML_TAG = re.compile(r"<[A-Za-z/]")
KEY_SHAPE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
LOOKUP_CALL = re.compile(r"""\b(?:t|tParts|tNodes)\(\s*(["'`])([^"'`$]*?)\1""")
I18N_ATTRIBUTE = re.compile(r"""\bdata-i18n(?:-[a-z-]+)?\s*=\s*(["'])([^"']*)\1""")
STRING_LITERAL = re.compile(r"""(["'`])([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)\1""")
SKIPPED_DIRS = frozenset({"node_modules", "dist", "coverage", "tests", "__tests__", "__pycache__", ".venv"})


@dataclass(frozen=True)
class App:
    """
    One app's catalogs, the sources that look keys up, and the keys exempt from the usage and identity rules.
    """

    name: str
    catalog_dir: str
    source_roots: tuple[str, ...]
    source_suffixes: frozenset[str]
    dynamic_prefixes: tuple[str, ...] = ()
    identical_keys: frozenset[str] = frozenset()


APPS = (
    App(
        name="lobby server",
        catalog_dir="backend/lobby/i18n/locales",
        source_roots=("backend/lobby",),
        source_suffixes=frozenset({".py", ".html"}),
        dynamic_prefixes=("auth.error.",),
    ),
    App(
        name="lobby scripts",
        catalog_dir="frontend/lobby/src/i18n/locales",
        source_roots=("frontend/lobby/src",),
        source_suffixes=frozenset({".ts"}),
        dynamic_prefixes=("occupancy.", "room.error."),
    ),
    App(
        name="game client",
        catalog_dir="frontend/game/src/i18n/locales",
        source_roots=("frontend/game/src", "frontend/game/index.html", "frontend/game/public"),
        source_suffixes=frozenset({".js", ".html"}),
    ),
)


@dataclass(frozen=True)
class Problem:
    path: Path
    key: str
    message: str

    def __str__(self) -> str:
        return f"{self.path.relative_to(ROOT)}: {self.key}: {self.message}"


type CatalogValue = str | dict[str, str]
type Catalog = dict[str, CatalogValue]


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise ValueError(f"duplicate keys {duplicates}")

    return dict(pairs)


def load_catalog(path: Path) -> tuple[Catalog | None, list[Problem]]:
    """
    Read one catalog file, returning it with the problems of its shape: JSON, value types and key order.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except FileNotFoundError:
        return None, [Problem(path, "-", "catalog file is missing")]
    except ValueError as e:
        return None, [Problem(path, "-", f"not valid JSON: {e}")]

    if not isinstance(data, dict):
        return None, [Problem(path, "-", "a catalog must be one JSON object")]

    problems: list[Problem] = []
    keys = list(data)
    if keys != sorted(keys):
        first_unsorted = next(b for a, b in itertools.pairwise(keys) if b < a)
        problems.append(Problem(path, first_unsorted, "keys are not sorted"))

    catalog: Catalog = {}
    for key, value in data.items():
        if not KEY_SHAPE.match(key):
            problems.append(Problem(path, key, "key must be dotted lower-case words"))

        if isinstance(value, str) or (isinstance(value, dict) and all(isinstance(v, str) for v in value.values())):
            catalog[key] = value
        else:
            problems.append(Problem(path, key, "value must be a string or a plural object of strings"))

    return catalog, problems


def _texts(value: CatalogValue) -> list[str]:
    return list(value.values()) if isinstance(value, dict) else [value]


def placeholders(value: CatalogValue) -> set[str]:
    """
    Return the placeholder names of a value; a plural value's are those of all its categories.
    """
    return {name for text in _texts(value) for name in PLACEHOLDER.findall(text)}


def check_value(path: Path, key: str, value: CatalogValue) -> list[Problem]:
    """
    Check one value on its own: no empty text, no HTML, no brace outside a placeholder.
    """
    problems = []
    for text in _texts(value):
        if not text.strip():
            problems.append(Problem(path, key, "empty or whitespace-only value"))

        if HTML_TAG.search(text):
            problems.append(Problem(path, key, "HTML in a value"))

        outside_placeholders = PLACEHOLDER.sub("", text)
        if "{" in outside_placeholders or "}" in outside_placeholders:
            problems.append(Problem(path, key, "brace outside a {name} placeholder"))

    return problems


def check_plural(path: Path, locale: str, key: str, value: CatalogValue, en_value: CatalogValue) -> list[Problem]:
    """
    Check a key's plural shape in one locale against en's and the locale's CLDR categories.
    """
    is_plural = isinstance(value, dict)
    if is_plural != isinstance(en_value, dict):
        return [Problem(path, key, "plural in one locale and not in another")]

    if not isinstance(value, dict):
        return []

    problems = []
    expected = PLURAL_CATEGORIES[locale]
    if set(value) != expected:
        problems.append(Problem(path, key, f"plural categories {sorted(value)} must be exactly {sorted(expected)}"))

    if locale == SOURCE_LOCALE and PLURAL_PARAM not in placeholders(value):
        problems.append(Problem(path, key, "plural value without {count}"))

    return problems


def check_catalogs(app: App, catalogs: dict[str, tuple[Path, Catalog]]) -> list[Problem]:
    """
    Check each locale's catalog against en: key sets, placeholders, plural shapes and untranslated values.
    """
    en_path, en = catalogs[SOURCE_LOCALE]
    problems = [problem for key, value in en.items() for problem in check_value(en_path, key, value)]
    problems.extend(problem for key, value in en.items() for problem in check_plural(en_path, "en", key, value, value))

    for locale in LOCALES:
        if locale == SOURCE_LOCALE or locale not in catalogs:
            continue

        path, catalog = catalogs[locale]
        problems.extend(Problem(path, key, "missing (present in en)") for key in sorted(en.keys() - catalog.keys()))
        problems.extend(Problem(path, key, "extra (absent from en)") for key in sorted(catalog.keys() - en.keys()))
        for key in sorted(catalog.keys() & en.keys()):
            value, en_value = catalog[key], en[key]
            problems.extend(check_value(path, key, value))
            problems.extend(check_plural(path, locale, key, value, en_value))
            if placeholders(value) != placeholders(en_value):
                problems.append(
                    Problem(
                        path,
                        key,
                        f"placeholders {sorted(placeholders(value))} differ from en's {sorted(placeholders(en_value))}",
                    )
                )

            if value == en_value and key not in app.identical_keys:
                problems.append(Problem(path, key, "identical to en (not in the identical-value allowlist)"))

    return problems


def iter_sources(app: App) -> list[Path]:
    """
    List the app's source files, leaving out dependencies, builds and tests.
    """
    files: list[Path] = []
    for root in app.source_roots:
        path = ROOT / root
        candidates = [path] if path.is_file() else sorted(path.rglob("*"))
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix not in app.source_suffixes:
                continue

            if SKIPPED_DIRS.intersection(candidate.relative_to(ROOT).parts):
                continue

            files.append(candidate)

    return files


def check_usage(app: App, en_path: Path, en: Catalog) -> list[Problem]:
    """
    Check that every literal key looked up in code exists in en, and every en key is used somewhere.

    A key counts as used when it appears in code as a whole string literal (a lookup, a data-i18n attribute or a
    constant naming it), or when it falls under one of the app's dynamic prefixes.
    """
    problems: list[Problem] = []
    used: set[str] = set()
    for source in iter_sources(app):
        text = source.read_text(encoding="utf-8")
        looked_up = [match[1] for match in LOOKUP_CALL.findall(text)]
        looked_up.extend(match[1] for match in I18N_ATTRIBUTE.findall(text))
        for key in looked_up:
            if not KEY_SHAPE.match(key):
                continue

            used.add(key)
            if key not in en:
                problems.append(Problem(source, key, f"looked up in code but absent from {en_path.name}"))

        used.update(match[1] for match in STRING_LITERAL.findall(text))

    unused = sorted(key for key in en.keys() - used if not key.startswith(app.dynamic_prefixes))
    problems.extend(Problem(en_path, key, "used nowhere in code and not under a dynamic prefix") for key in unused)

    return problems


def check_app(app: App) -> list[Problem]:
    """
    Run every rule over one app's three catalogs and its sources.
    """
    problems: list[Problem] = []
    catalogs: dict[str, tuple[Path, Catalog]] = {}
    for locale in LOCALES:
        path = ROOT / app.catalog_dir / f"{locale}.json"
        catalog, load_problems = load_catalog(path)
        problems.extend(load_problems)
        if catalog is not None:
            catalogs[locale] = (path, catalog)

    if SOURCE_LOCALE not in catalogs:
        return problems

    problems.extend(check_catalogs(app, catalogs))
    en_path, en = catalogs[SOURCE_LOCALE]
    problems.extend(check_usage(app, en_path, en))
    return problems


def main() -> int:
    problems = [problem for app in APPS for problem in check_app(app)]
    sys.stderr.writelines(f"{problem}\n" for problem in problems)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
