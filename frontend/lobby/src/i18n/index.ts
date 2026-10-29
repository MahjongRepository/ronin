import { type TemplateResult } from "lit-html";

import en from "@/i18n/locales/en.json";
import ja from "@/i18n/locales/ja.json";
import ru from "@/i18n/locales/ru.json";

const LOCALES = ["en", "ja", "ru"] as const;
const DEFAULT_LOCALE = "en";
const PLURAL_PARAM = "count";
const PLACEHOLDER = /\{(?<name>[a-z][a-z0-9_]*)\}/g;

type Locale = (typeof LOCALES)[number];
type MessageKey = keyof typeof en;
type PluralForms = Readonly<Partial<Record<Intl.LDMLPluralRule, string>>>;
type Message = string | PluralForms;
type Catalog = Readonly<Record<string, Message>>;
type Params = Readonly<Record<string, string | number>>;
type PartParams = Readonly<Record<string, string | number | TemplateResult>>;
type Part = string | TemplateResult;

const CATALOGS: Readonly<Record<Locale, Catalog>> = { en, ja, ru };

const reportedKeys = new Set<string>();

class I18nError extends Error {
    readonly key: string;
    readonly reason: string;

    constructor(key: string, reason: string) {
        super(`${key}: ${reason}`);
        this.key = key;
        this.reason = reason;
    }
}

function isLocale(value: string): value is Locale {
    return LOCALES.some((locale) => locale === value);
}

function pageLocale(): Locale {
    const { lang } = document.documentElement;
    return isLocale(lang) ? lang : DEFAULT_LOCALE;
}

function isMessageKey(key: string): key is MessageKey {
    return Object.hasOwn(en, key);
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

function formatNumber(value: number): string {
    return new Intl.NumberFormat(pageLocale()).format(value);
}

function formatList(items: readonly string[]): string {
    return new Intl.ListFormat(pageLocale(), { type: "conjunction" }).format(items);
}

function formatTime(date: Date): string {
    return date.toLocaleTimeString(pageLocale(), { hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(date: Date): string {
    return new Intl.DateTimeFormat(pageLocale(), {
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        month: "short",
    }).format(date);
}

function checkParams(key: string, source: Message, params: PartParams): void {
    const expected = placeholders(source);
    const given = Object.keys(params);
    if (typeof source === "string" && PLURAL_PARAM in params) {
        throw new I18nError(key, "not a plural key");
    }
    const missing = [...expected].filter((name) => !Object.hasOwn(params, name));
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

function pickText(key: string, message: Message, params: PartParams): string {
    if (typeof message === "string") {
        return message;
    }
    const count = params[PLURAL_PARAM];
    if (typeof count !== "number") {
        throw new I18nError(key, "plural count is not a number");
    }
    return pluralText(message, pageLocale(), count);
}

function splitMessage(text: string, params: PartParams): Part[] {
    return text.split(PLACEHOLDER).map((piece, index) => {
        if (index % 2 === 0) {
            return piece;
        }
        if (!Object.hasOwn(params, piece)) {
            return `{${piece}}`;
        }
        const value = params[piece];
        return typeof value === "number" ? formatNumber(value) : value;
    });
}

function renderFallback(key: string, params: PartParams): Part[] {
    if (!isMessageKey(key)) {
        return [key];
    }
    const source: Message = en[key];
    if (typeof source === "string") {
        return splitMessage(source, params);
    }
    const count = params[PLURAL_PARAM];
    const text =
        typeof count === "number"
            ? pluralText(source, DEFAULT_LOCALE, count)
            : (source.other ?? "");
    return splitMessage(text, params);
}

function renderMessage(key: string, params: PartParams): Part[] {
    if (!isMessageKey(key)) {
        throw new I18nError(key, "missing key");
    }
    checkParams(key, en[key], params);
    const locale = pageLocale();
    const catalog = CATALOGS[locale];
    if (!Object.hasOwn(catalog, key)) {
        throw new I18nError(key, `missing ${locale} translation`);
    }
    return splitMessage(pickText(key, catalog[key], params), params);
}

function lookupParts(key: string, params: PartParams): Part[] {
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

function t(key: MessageKey, params: Params = {}): string {
    return lookupParts(key, params).join("");
}

function tParts(key: MessageKey, params: PartParams): Part[] {
    return lookupParts(key, params);
}

function applyStaticText(root: ParentNode): void {
    for (const element of root.querySelectorAll<HTMLElement>("[data-i18n]")) {
        element.textContent = lookupParts(element.dataset.i18n ?? "", {}).join("");
    }
    for (const element of root.querySelectorAll<HTMLElement>("[data-i18n-aria-label]")) {
        const key = element.dataset.i18nAriaLabel ?? "";
        element.setAttribute("aria-label", lookupParts(key, {}).join(""));
    }
}

export {
    I18nError,
    applyStaticText,
    formatDateTime,
    formatList,
    formatNumber,
    formatTime,
    isLocale,
    isMessageKey,
    pageLocale,
    reportI18nError,
    t,
    tParts,
};
export type { Locale, MessageKey, Params };
