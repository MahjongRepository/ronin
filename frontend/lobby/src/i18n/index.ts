import { createTranslator } from "@ronin/shared/i18n";

import en from "@/i18n/locales/en.json";
import ja from "@/i18n/locales/ja.json";
import ru from "@/i18n/locales/ru.json";

type MessageKey = keyof typeof en;

const { isMessageKey, t, tParts } = createTranslator({ en, ja, ru });

export {
    formatDate,
    formatDateTime,
    formatList,
    formatNumber,
    formatTime,
} from "@ronin/shared/format";
export { I18nError, reportI18nError } from "@ronin/shared/i18n";
export { isLocale, pageLocale } from "@ronin/shared/locale";
export type { Locale } from "@ronin/shared/locale";
export { isMessageKey, t, tParts };
export type { MessageKey };
