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
LOOKUP_CALL = re.compile(
    r"""\b(?:t|tParts|tNodes|translate|translate_markup|translate_for_request)\("""
    r"""\s*(?:[A-Za-z_][\w.]*\s*,\s*)?(["'`])([^"'`$]*?)\1"""
)
I18N_ATTRIBUTE = re.compile(r"""\bdata-i18n(?:-([a-z-]+))?\s*=\s*(["'])([^"']*)\2""")
NON_KEY_I18N_ATTRIBUTES = frozenset({"slot", "params"})
STRING_LITERAL = re.compile(r"""(["'`])([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)\1""")
QUOTED_LITERAL = re.compile(r"""(["'])([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)\1""")
FILE_NAME_SUFFIXES = (".html", ".json", ".js", ".ts", ".py")
SKIPPED_DIRS = frozenset({"node_modules", "dist", "coverage", "tests", "__tests__", "__pycache__", ".venv"})


@dataclass(frozen=True)
class App:
    """
    One app's catalogs, the sources that look keys up, and the keys exempt from the usage and identity rules.

    ``markup_roots`` hold another app's server-rendered markup whose ``data-i18n`` keys this app writes again in place
    (the lobby scripts re-render the lobby templates' chrome on a language switch): only those attributes count there.
    """

    name: str
    catalog_dir: str
    source_roots: tuple[str, ...]
    source_suffixes: frozenset[str]
    dynamic_prefixes: tuple[str, ...] = ()
    identical_keys: frozenset[str] = frozenset()
    literals_in_namespaces_are_keys: bool = False
    markup_roots: tuple[str, ...] = ()


APPS = (
    App(
        name="lobby server",
        catalog_dir="backend/lobby/i18n/locales",
        source_roots=("backend/lobby",),
        source_suffixes=frozenset({".py", ".html"}),
        dynamic_prefixes=("auth.error.",),
        literals_in_namespaces_are_keys=True,
    ),
    App(
        name="lobby scripts",
        catalog_dir="frontend/lobby/src/i18n/locales",
        source_roots=("frontend/lobby/src",),
        source_suffixes=frozenset({".ts"}),
        dynamic_prefixes=("occupancy.", "room.error."),
        markup_roots=("backend/lobby/views/templates",),
    ),
    App(
        name="game client",
        catalog_dir="frontend/game/src/i18n/locales",
        source_roots=("frontend/game/src", "frontend/game/index.html", "frontend/game/public"),
        source_suffixes=frozenset({".js", ".html"}),
        dynamic_prefixes=(
            "draw.",
            "game.error.",
            "game.meld.",
            "game.score.yakuman_",
            "game.session_error.",
            "game.summary.rank_",
            "replay.speed.",
            "round.",
            "tile.",
            "wind.",
            "yaku.",
        ),
        identical_keys=frozenset(
            {"game.settings.off", "game.settings.on", "list.separator", "replay.seat_option", "replay.start"}
        ),
        literals_in_namespaces_are_keys=True,
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


def iter_sources(roots: tuple[str, ...], suffixes: frozenset[str]) -> list[Path]:
    """
    List the source files under ``roots`` with one of ``suffixes``, leaving out dependencies, builds and tests.
    """
    files: list[Path] = []
    for root in roots:
        path = ROOT / root
        candidates = [path] if path.is_file() else sorted(path.rglob("*"))
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix not in suffixes:
                continue

            if SKIPPED_DIRS.intersection(candidate.relative_to(ROOT).parts):
                continue

            files.append(candidate)

    return files


def attribute_keys(text: str) -> list[str]:
    """
    Return the keys named by the ``data-i18n`` attributes of ``text``, leaving out those that hold no key.
    """
    return [value for name, _, value in I18N_ATTRIBUTE.findall(text) if name not in NON_KEY_I18N_ATTRIBUTES]


def check_looked_up(source: Path, looked_up: list[str], en_path: Path, en: Catalog) -> list[Problem]:
    """
    Check the keys one source looks up: each must be shaped like a key and present in en.
    """
    problems = []
    for key in sorted(set(looked_up)):
        if not KEY_SHAPE.match(key):
            problems.append(Problem(source, key, "looked up in code but not dotted lower-case words"))
            continue

        if key not in en:
            problems.append(Problem(source, key, f"looked up in code but absent from {en_path.name}"))

    return problems


def check_usage(app: App, en_path: Path, en: Catalog) -> list[Problem]:
    """
    Check that every literal key looked up in code exists in en, and every en key is used somewhere.

    A key counts as used when it appears in code as a whole string literal (a lookup, a data-i18n attribute or a
    constant naming it), or when it falls under one of the app's dynamic prefixes. A literal lookup or data-i18n
    attribute whose value is not shaped like a key fails; `data-i18n-slot` and `data-i18n-params` hold no key. In an app whose code holds keys in
    tables and constants (the lobby server's error pages and notices), every dotted literal whose first word is one of
    the catalog's namespaces counts as a lookup too, so a typo in a table fails like one in a call. In the app's markup
    roots only the data-i18n attributes count.
    """
    problems: list[Problem] = []
    used: set[str] = set()
    namespaces = {key.split(".")[0] for key in en}
    markup = iter_sources(app.markup_roots, frozenset({".html"}))
    for source in markup:
        looked_up = attribute_keys(source.read_text(encoding="utf-8"))
        problems.extend(check_looked_up(source, looked_up, en_path, en))
        used.update(key for key in looked_up if KEY_SHAPE.match(key))

    for source in iter_sources(app.source_roots, app.source_suffixes):
        text = source.read_text(encoding="utf-8")
        looked_up = attribute_keys(text) + [match[1] for match in LOOKUP_CALL.findall(text)]
        if app.literals_in_namespaces_are_keys:
            literals = (match[1] for match in QUOTED_LITERAL.findall(text))
            looked_up.extend(
                key for key in literals if key.split(".")[0] in namespaces and not key.endswith(FILE_NAME_SUFFIXES)
            )

        problems.extend(check_looked_up(source, looked_up, en_path, en))
        used.update(key for key in looked_up if KEY_SHAPE.match(key))
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
