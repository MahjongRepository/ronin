import { type Locale, langCookie } from "./locale";
import { resetWindScript } from "./winds";

export function switchLocale(locale: Locale): void {
    document.cookie = langCookie(locale, window.location.protocol);
    document.documentElement.lang = locale;
    resetWindScript();
}
