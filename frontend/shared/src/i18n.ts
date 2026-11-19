import { type TemplateResult } from "lit-html";

import { formatNumber } from "./format";
import { DEFAULT_LOCALE, type Locale, pageLocale } from "./locale";

const PLURAL_PARAM = "count";
const PLACEHOLDER = /\{(?<name>[a-z][a-z0-9_]*)\}/g;

type PluralForms = Readonly<Partial<Record<Intl.LDMLPluralRule, string>>>;
type Message = string | PluralForms;
type Catalog = Readonly<Record<string, Message>>;
type Params = Readonly<Record<string, string | number>>;
type PartParams = Readonly<Record<string, string | number | TemplateResult>>;
type Part = string | TemplateResult;

interface Translator<Key extends string> {
    readonly isMessageKey: (key: string) => key is Key;
    readonly t: (key: Key, params?: Params) => string;
    readonly tParts: (key: Key, params: PartParams) => Part[];
}

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

function hasKey(record: object, key: string): boolean {
    return Object.getOwnPropertyDescriptor(record, key) !== undefined;
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

function checkParams(key: string, source: Message, params: PartParams): void {
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
        if (!hasKey(params, piece)) {
            return `{${piece}}`;
        }
        const value = params[piece];
        return typeof value === "number" ? formatNumber(value) : value;
    });
}

function renderFallback(source: Message | undefined, key: string, params: PartParams): Part[] {
    if (source === undefined) {
        return [key];
    }
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

function renderMessage(
    catalogs: Readonly<Record<Locale, Catalog>>,
    key: string,
    params: PartParams,
): Part[] {
    const source = catalogs[DEFAULT_LOCALE];
    if (!hasKey(source, key)) {
        throw new I18nError(key, "missing key");
    }
    checkParams(key, source[key], params);
    const locale = pageLocale();
    const catalog = catalogs[locale];
    if (!hasKey(catalog, key)) {
        throw new I18nError(key, `missing ${locale} translation`);
    }
    return splitMessage(pickText(key, catalog[key], params), params);
}

function createTranslator<Source extends Catalog>(
    catalogs: Readonly<Record<Locale, Catalog>> & { readonly en: Source },
): Translator<Extract<keyof Source, string>> {
    type Key = Extract<keyof Source, string>;
    const source: Catalog = catalogs[DEFAULT_LOCALE];

    function isMessageKey(key: string): key is Key {
        return hasKey(source, key);
    }

    function lookupParts(key: string, params: PartParams): Part[] {
        try {
            return renderMessage(catalogs, key, params);
        } catch (error) {
            if (!(error instanceof I18nError) || import.meta.env.DEV) {
                throw error;
            }
            reportI18nError(key, error.reason);
            return renderFallback(isMessageKey(key) ? source[key] : undefined, key, params);
        }
    }

    return {
        isMessageKey,
        t: (key, params = {}) => lookupParts(key, params).join(""),
        tParts: (key, params) => lookupParts(key, params),
    };
}

export { I18nError, createTranslator, reportI18nError };
export type { Params, Part, PartParams, Translator };
