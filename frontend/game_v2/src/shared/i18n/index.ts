import { createTranslator } from "@ronin/shared/i18n";
import { type Locale, langCookie } from "@ronin/shared/locale";

import en from "./locales/en.json";
import ja from "./locales/ja.json";
import ru from "./locales/ru.json";
import { resetWindScript } from "./winds";

type MessageKey = keyof typeof en;

const { isMessageKey, t } = createTranslator({ en, ja, ru });

function applyPageLocale(locale: Locale): void {
    document.cookie = langCookie(locale, window.location.protocol);
    document.documentElement.lang = locale;
    resetWindScript();
    document.title = t("game.page.title");
}

export { formatList, formatNumber } from "@ronin/shared/format";
export { I18nError, reportI18nError } from "@ronin/shared/i18n";
export { LOCALES, isLocale, langCookie, pageLocale, resolveLocale } from "@ronin/shared/locale";
export type { Locale } from "@ronin/shared/locale";
export {
    WIND_LETTERS,
    WIND_SCRIPT_KEY,
    WIND_SCRIPT_LANGS,
    applyWindScript,
    pageWindScript,
    restoreWindScript,
    windScriptsOf,
} from "./winds";
export type { WindScript } from "./winds";
export { applyPageLocale, isMessageKey, t };
export type { MessageKey };
