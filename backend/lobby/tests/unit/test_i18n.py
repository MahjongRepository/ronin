import json
import logging

import pytest
from markupsafe import Markup

from lobby.i18n import CatalogError, I18nError, Locale, Translator, load_catalogs
from lobby.i18n.locale import resolve_locale
from lobby.i18n.translator import plural_category
from lobby.views.handlers import _LOBBY_NOTICES
from shared.auth.service import AuthErrorCode

CATALOGS = {
    Locale.EN: {
        "auth.login.no_account": "Don't have an account? {register}",
        "auth.login.title": "Log in",
        "history.rounds": {"one": "{count} round", "other": "{count} rounds"},
    },
    Locale.JA: {
        "auth.login.no_account": "アカウントがない場合は{register}",
        "auth.login.title": "ログイン",
        "history.rounds": {"other": "{count}局"},
    },
    Locale.RU: {
        "auth.login.no_account": "Нет аккаунта? {register}",
        "auth.login.title": "Вход",
        "history.rounds": {
            "one": "{count} раунд",
            "few": "{count} раунда",
            "many": "{count} раундов",
            "other": "{count} раунда",
        },
    },
}


class TestResolveLocale:
    def test_resolve_locale__when_cookie_is_valid__should_beat_accept_language(self):
        resolved = resolve_locale(cookie="ja", accept_language="ru")
        assert resolved.locale == Locale.JA
        assert resolved.from_cookie

    def test_resolve_locale__when_cookie_is_not_a_supported_code__should_ignore_it(self):
        resolved = resolve_locale(cookie="JA", accept_language="ru")
        assert resolved.locale == Locale.RU
        assert not resolved.from_cookie

    def test_resolve_locale__when_accept_language_has_q_values__should_pick_the_best_supported_primary_tag(self):
        resolved = resolve_locale(cookie=None, accept_language="fr;q=1, ru-RU;q=0.8, ja;q=0.5")
        assert resolved.locale == Locale.RU

    def test_resolve_locale__when_neither_cookie_nor_header__should_default_to_en(self):
        resolved = resolve_locale(cookie=None, accept_language=None)
        assert resolved.locale == Locale.EN
        assert not resolved.from_cookie


class TestTranslator:
    @pytest.mark.parametrize(
        ("key", "params"),
        [
            ("auth.login.missing", {}),
            ("auth.login.title", {"name": "dev"}),
            ("auth.login.no_account", {}),
            ("history.rounds", {}),
            ("history.rounds", {"count": "3"}),
            ("auth.login.title", {"count": 3}),
        ],
        ids=["missing_key", "extra_param", "missing_param", "plural_without_count", "non_numeric_count", "not_plural"],
    )
    def test_translate__when_strict_and_call_does_not_match_the_catalog__should_raise(self, key, params):
        translator = Translator(catalogs=CATALOGS, strict=True)

        with pytest.raises(I18nError):
            translator.translate(Locale.RU, key, **params)

    def test_translate__when_not_strict_and_call_does_not_match__should_render_en_and_warn_once_per_key(self, caplog):
        translator = Translator(catalogs=CATALOGS, strict=False)

        with caplog.at_level(logging.WARNING):
            first = translator.translate(Locale.RU, "auth.login.title", name="dev")
            second = translator.translate(Locale.JA, "auth.login.title", name="dev")
        assert first == second == "Log in"
        warnings = [record for record in caplog.records if "i18n error" in record.getMessage()]
        assert len(warnings) == 1
        assert "auth.login.title" in warnings[0].getMessage()
        assert "ru" in warnings[0].getMessage()

    def test_translate__when_plural__should_pick_the_locale_form_and_format_the_count(self):
        translator = Translator(catalogs=CATALOGS, strict=True)

        assert translator.translate(Locale.RU, "history.rounds", count=22) == "22 раунда"
        assert (
            translator.translate(Locale.RU, "history.rounds", count=25000) == "25\N{NARROW NO-BREAK SPACE}000 раундов"
        )
        assert translator.translate(Locale.EN, "history.rounds", count=1) == "1 round"

    def test_translate_markup__when_slot_is_markup__should_escape_text_params_but_keep_the_slot(self):
        translator = Translator(catalogs=CATALOGS, strict=True)

        link = translator.translate_markup(Locale.EN, "auth.login.no_account", register=Markup('<a href="/r">R</a>'))
        text = translator.translate_markup(Locale.EN, "auth.login.no_account", register="<script>")
        assert link == Markup('Don&#39;t have an account? <a href="/r">R</a>')
        assert text == Markup("Don&#39;t have an account? &lt;script&gt;")


@pytest.mark.parametrize(
    ("count", "category"),
    [(1, "one"), (2, "few"), (5, "many"), (11, "many"), (12, "many"), (21, "one"), (22, "few"), (111, "many")],
)
def test_plural_category__when_ru__should_follow_the_cldr_integer_rule(count, category):
    assert plural_category(Locale.RU, count) == category


def test_load_catalogs__when_a_locale_lacks_an_en_key__should_refuse_to_load(tmp_path):
    for locale, catalog in CATALOGS.items():
        (tmp_path / f"{locale}.json").write_text(json.dumps(catalog))
    (tmp_path / "ja.json").write_text(json.dumps({"auth.login.title": "ログイン"}))

    with pytest.raises(CatalogError, match="keys differ"):
        load_catalogs(tmp_path)


_AUTH_ERROR_PARAMS = {
    AuthErrorCode.WRONG_CREDENTIALS: {},
    AuthErrorCode.USERNAME_TAKEN: {"username": "dev"},
    AuthErrorCode.USERNAME_LENGTH: {"min": 3, "max": 30},
    AuthErrorCode.USERNAME_PATTERN: {},
    AuthErrorCode.PASSWORD_LENGTH: {"min": 8, "max": 72},
    AuthErrorCode.PASSWORD_BYTES: {"max": 72},
    AuthErrorCode.HUMAN_ACCOUNT: {"username": "dev"},
    AuthErrorCode.ACCOUNT_NOT_SAVED: {},
}


@pytest.mark.parametrize("locale", list(Locale))
def test_lobby_catalog__when_walking_auth_error_codes_and_notices__should_render_every_one_strictly(locale):
    translator = Translator(catalogs=load_catalogs(), strict=True)

    auth_errors = [
        translator.translate(locale, f"auth.error.{code}", **_AUTH_ERROR_PARAMS[code]) for code in AuthErrorCode
    ]
    notices = [translator.translate(locale, key) for key in _LOBBY_NOTICES.values()]
    assert all(auth_errors)
    assert all(notices)
