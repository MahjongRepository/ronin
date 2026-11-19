import { createTranslator } from "./i18n";
import en from "./locales/en.json";
import ja from "./locales/ja.json";
import ru from "./locales/ru.json";

export const { t } = createTranslator({ en, ja, ru });
