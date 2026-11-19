import { I18nError, createTranslator, reportI18nError } from "@ronin/shared/i18n";

import en from "@/i18n/locales/en.json";
import ja from "@/i18n/locales/ja.json";
import ru from "@/i18n/locales/ru.json";

type MessageKey = keyof typeof en;

const { isMessageKey, t, tParts } = createTranslator({ en, ja, ru });

function staticText(key: string): string {
    if (isMessageKey(key)) {
        return t(key);
    }
    if (import.meta.env.DEV) {
        throw new I18nError(key, "missing key");
    }
    reportI18nError(key, "missing key");
    return key;
}

function applyStaticText(root: ParentNode): void {
    for (const element of root.querySelectorAll<HTMLElement>("[data-i18n]")) {
        element.textContent = staticText(element.dataset.i18n ?? "");
    }
    for (const element of root.querySelectorAll<HTMLElement>("[data-i18n-aria-label]")) {
        element.setAttribute("aria-label", staticText(element.dataset.i18nAriaLabel ?? ""));
    }
}

export { formatDateTime, formatList, formatNumber, formatTime } from "@ronin/shared/format";
export { I18nError, reportI18nError } from "@ronin/shared/i18n";
export { isLocale, pageLocale } from "@ronin/shared/locale";
export type { Locale } from "@ronin/shared/locale";
export { applyStaticText, isMessageKey, t, tParts };
export type { MessageKey };
