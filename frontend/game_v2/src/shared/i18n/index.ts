import { createTranslator } from "@ronin/shared/i18n";
import { type Locale } from "@ronin/shared/locale";
import { switchLocale } from "@ronin/shared/locale-switch";

import en from "./locales/en.json";
import ja from "./locales/ja.json";
import ru from "./locales/ru.json";

type MessageKey = keyof typeof en;

const { isMessageKey, t } = createTranslator({ en, ja, ru });

function applyPageLocale(locale: Locale): void {
    switchLocale(locale);
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
} from "@ronin/shared/winds";
export type { WindScript } from "@ronin/shared/winds";
export { applyPageLocale, isMessageKey, t };
export type { MessageKey };
