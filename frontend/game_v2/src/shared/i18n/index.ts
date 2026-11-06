import { DEFAULT_LOCALE, type Locale, isLocale, langCookie } from "./locale";
import en from "./locales/en.json";
import ja from "./locales/ja.json";
import ru from "./locales/ru.json";

const PLURAL_PARAM = "count";
const PLACEHOLDER = /\{(?<name>[a-z][a-z0-9_]*)\}/g;

type MessageKey = keyof typeof en;
type PluralForms = Readonly<Partial<Record<Intl.LDMLPluralRule, string>>>;
type Message = string | PluralForms;
type Catalog = Readonly<Record<string, Message>>;
type Params = Readonly<Record<string, string | number>>;

const CATALOGS: Readonly<Record<Locale, Catalog>> = { en, ja, ru };

const reportedKeys = new Set<string>();

class I18nError extends Error {
    override readonly name = "I18nError";
    readonly key: string;
    readonly reason: string;

    constructor(key: string, reason: string) {
        super(`${key}: ${reason}`);
        this.key = key;
        this.reason = reason;
    }
}

function pageLocale(): Locale {
    const { lang } = document.documentElement;
    return isLocale(lang) ? lang : DEFAULT_LOCALE;
}

function hasKey(record: object, key: string): boolean {
    return Object.getOwnPropertyDescriptor(record, key) !== undefined;
}

function isMessageKey(key: string): key is MessageKey {
    return hasKey(en, key);
}

function reportI18nError(key: string, reason: string): void {
    if (reportedKeys.has(key)) {
        return;
    }
    reportedKeys.add(key);
    console.error("i18n error", { key, locale: pageLocale(), reason });
}

function placeholders(message: Message): Set<string> {
    const texts = typeof message === "string" ? [message] : Object.values(message);
    return new Set(
        texts.flatMap((text) => [...(text ?? "").matchAll(PLACEHOLDER)].map((m) => m[1])),
    );
}

function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
    return new Intl.NumberFormat(pageLocale(), options).format(value);
}

function formatList(items: readonly string[]): string {
    return new Intl.ListFormat(pageLocale(), { type: "conjunction" }).format(items);
}

function checkParams(key: string, source: Message, params: Params): void {
    const expected = placeholders(source);
    const given = Object.keys(params);
    if (typeof source === "string" && PLURAL_PARAM in params) {
        throw new I18nError(key, "not a plural key");
    }
    const missing = [...expected].filter((name) => !hasKey(params, name));
    if (missing.length > 0) {
        throw new I18nError(key, `missing params ${missing.join(", ")}`);
    }
    const extra = given.filter((name) => !expected.has(name));
    if (extra.length > 0) {
        throw new I18nError(key, `unexpected params ${extra.join(", ")}`);
    }
}

function pluralText(forms: PluralForms, locale: Locale, count: number): string {
    return forms[new Intl.PluralRules(locale).select(count)] ?? forms.other ?? "";
}

function pickText(key: string, message: Message, params: Params): string {
    if (typeof message === "string") {
        return message;
    }
    const count = params[PLURAL_PARAM];
    if (typeof count !== "number") {
        throw new I18nError(key, "plural count is not a number");
    }
    return pluralText(message, pageLocale(), count);
}

function fillMessage(text: string, params: Params): string {
    return text
        .split(PLACEHOLDER)
        .map((piece, index) => {
            if (index % 2 === 0) {
                return piece;
            }
            if (!hasKey(params, piece)) {
                return `{${piece}}`;
            }
            const value = params[piece];
            return typeof value === "number" ? formatNumber(value) : value;
        })
        .join("");
}

function renderFallback(key: string, params: Params): string {
    if (!isMessageKey(key)) {
        return key;
    }
    const source = CATALOGS[DEFAULT_LOCALE][key];
    if (typeof source === "string") {
        return fillMessage(source, params);
    }
    const count = params[PLURAL_PARAM];
    const text =
        typeof count === "number"
            ? pluralText(source, DEFAULT_LOCALE, count)
            : (source.other ?? "");
    return fillMessage(text, params);
}

function renderMessage(key: string, params: Params): string {
    if (!isMessageKey(key)) {
        throw new I18nError(key, "missing key");
    }
    checkParams(key, en[key], params);
    const locale = pageLocale();
    const catalog = CATALOGS[locale];
    if (!hasKey(catalog, key)) {
        throw new I18nError(key, `missing ${locale} translation`);
    }
    return fillMessage(pickText(key, catalog[key], params), params);
}

function t(key: MessageKey, params: Params = {}): string {
    try {
        return renderMessage(key, params);
    } catch (error) {
        if (!(error instanceof I18nError) || import.meta.env.DEV) {
            throw error;
        }
        reportI18nError(key, error.reason);
        return renderFallback(key, params);
    }
}

function applyPageLocale(locale: Locale): void {
    document.cookie = langCookie(locale, window.location.protocol);
    document.documentElement.lang = locale;
    document.title = t("game.page.title");
}

export { LOCALES, isLocale, langCookie, resolveLocale } from "./locale";
export type { Locale } from "./locale";
export {
    I18nError,
    applyPageLocale,
    formatList,
    formatNumber,
    isMessageKey,
    pageLocale,
    reportI18nError,
    t,
};
export type { MessageKey };
