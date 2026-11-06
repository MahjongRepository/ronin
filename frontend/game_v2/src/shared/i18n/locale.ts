export const LOCALES = ["en", "ja", "ru"] as const;
export const DEFAULT_LOCALE = "en";

export type Locale = (typeof LOCALES)[number];

const LANG_COOKIE = "lang";
const LANG_COOKIE_MAX_AGE_SECONDS = 31_536_000;

export function isLocale(value: string): value is Locale {
    return LOCALES.some((locale) => locale === value);
}

function cookieValue(cookies: string, name: string): string | undefined {
    for (const pair of cookies.split(";")) {
        const separator = pair.indexOf("=");
        if (separator !== -1 && pair.slice(0, separator).trim() === name) {
            return pair.slice(separator + 1).trim();
        }
    }
    return undefined;
}

function browserLocale(browserLanguages: readonly string[]): Locale | undefined {
    for (const language of browserLanguages) {
        const primary = language.split("-")[0].toLowerCase();
        if (isLocale(primary)) {
            return primary;
        }
    }
    return undefined;
}

export function resolveLocale(cookies: string, browserLanguages: readonly string[]): Locale {
    const chosen = cookieValue(cookies, LANG_COOKIE);
    if (chosen !== undefined && isLocale(chosen)) {
        return chosen;
    }
    return browserLocale(browserLanguages) ?? DEFAULT_LOCALE;
}

export function langCookie(locale: Locale, protocol: string): string {
    const cookie = `${LANG_COOKIE}=${locale}; Path=/; Max-Age=${String(LANG_COOKIE_MAX_AGE_SECONDS)}; SameSite=Lax`;
    return protocol === "https:" ? `${cookie}; Secure` : cookie;
}
