import en from "./locales/en.json";
import ja from "./locales/ja.json";
import ru from "./locales/ru.json";

export const LOCALES = Object.freeze(["en", "ja", "ru"]);
export const DEFAULT_LOCALE = "en";

/** Each locale by its native name, as the language choices show it. */
export const LANGUAGE_NAMES = Object.freeze({ en: "English", ja: "日本語", ru: "Русский" });

/** The cookie the lobby's POST /lang writes too: same name, path and attributes (docs/i18n.md). */
const LANG_COOKIE = "lang";
const LANG_COOKIE_MAX_AGE_SECONDS = 365 * 24 * 60 * 60;

const PLURAL_PARAM = "count";
const PLACEHOLDER = /\{([a-z][a-z0-9_]*)\}/g;
const CATALOGS = Object.freeze({ en, ja, ru });

/** The attributes `applyStaticText` fills, each from the key in its `data-i18n-…` attribute. */
const STATIC_ATTRIBUTES = Object.freeze({
    "data-i18n-title": "title",
    "data-i18n-aria-label": "aria-label",
    "data-i18n-alt": "alt",
});

const reportedKeys = new Set();

let current = null;

export class I18nError extends Error {
    constructor(key, reason) {
        super(`${key}: ${reason}`);
        this.name = "I18nError";
        this.key = key;
        this.reason = reason;
    }
}

export function isLocale(value) {
    return LOCALES.includes(value);
}

/** The page's locale: the `<html lang>` that `public/locale.js` resolved before the bundle ran, read once. */
export function locale() {
    if (current === null) {
        const { lang } = document.documentElement;
        current = isLocale(lang) ? lang : DEFAULT_LOCALE;
    }
    return current;
}

/** Switch the page to `next`: every later lookup uses it, and `<html lang>` says it. */
export function setLocale(next) {
    if (!isLocale(next)) {
        throw new I18nError(String(next), "unsupported locale");
    }
    current = next;
    document.documentElement.lang = next;
}

/** Remember an explicit choice in the `lang` cookie, which the lobby reads too. */
export function writeLangCookie(chosen) {
    if (!isLocale(chosen)) {
        throw new I18nError(String(chosen), "unsupported locale");
    }
    const secure = window.location.protocol === "https:" ? "; Secure" : "";
    document.cookie = `${LANG_COOKIE}=${chosen}; Path=/; Max-Age=${LANG_COOKIE_MAX_AGE_SECONDS}; SameSite=Lax${secure}`;
}

/** Report an i18n problem once per key: the production fallback's diagnostic. */
export function reportI18nError(key, reason) {
    if (reportedKeys.has(key)) {
        return;
    }
    reportedKeys.add(key);
    console.error("i18n error", { key, locale: locale(), reason });
}

export function hasKey(key) {
    return Object.hasOwn(en, key);
}

export function formatNumber(value) {
    return new Intl.NumberFormat(locale()).format(value);
}

function placeholders(message) {
    const texts = typeof message === "string" ? [message] : Object.values(message);
    return new Set(texts.flatMap((text) => [...text.matchAll(PLACEHOLDER)].map((m) => m[1])));
}

function checkParams(key, source, params) {
    if (typeof source === "string" && Object.hasOwn(params, PLURAL_PARAM)) {
        throw new I18nError(key, "not a plural key");
    }
    if (typeof source !== "string" && typeof params[PLURAL_PARAM] !== "number") {
        throw new I18nError(key, "plural count is not a number");
    }
    const expected = placeholders(source);
    const missing = [...expected].filter((name) => !Object.hasOwn(params, name));
    if (missing.length > 0) {
        throw new I18nError(key, `missing params ${missing.join(", ")}`);
    }
    const extra = Object.keys(params).filter((name) => !expected.has(name));
    if (extra.length > 0) {
        throw new I18nError(key, `unexpected params ${extra.join(", ")}`);
    }
}

function pickText(message, localeName, params) {
    if (typeof message === "string") {
        return message;
    }
    const count = params[PLURAL_PARAM];
    const category =
        typeof count === "number" ? new Intl.PluralRules(localeName).select(count) : "other";
    return message[category] ?? message.other;
}

/** A value's text split into its literal pieces and its params: numbers in the locale's format, nodes as they are. */
function splitText(text, params) {
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

function renderParts(key, params) {
    if (!hasKey(key)) {
        throw new I18nError(key, "missing key");
    }
    checkParams(key, en[key], params);
    const message = CATALOGS[locale()][key] ?? en[key];
    return splitText(pickText(message, locale(), params), params);
}

function renderFallback(key, params) {
    if (!hasKey(key)) {
        return [key];
    }
    return splitText(pickText(en[key], DEFAULT_LOCALE, params), params);
}

/** A key's parts, strict under the dev server and Vitest; in production a broken lookup falls back to English. */
function lookupParts(key, params) {
    try {
        return renderParts(key, params);
    } catch (error) {
        if (!(error instanceof I18nError) || import.meta.env.DEV) {
            throw error;
        }
        reportI18nError(key, error.reason);
        return renderFallback(key, params);
    }
}

/** A key's text in the page's locale, its `{name}` placeholders filled from `params`. */
export function t(key, params = {}) {
    return lookupParts(key, params)
        .map((part) => (typeof part === "string" ? part : part.textContent))
        .join("");
}

/**
 * A key's text as DOM nodes, for a sentence with an element in it (a link slot): each piece of text a text node, never
 * parsed as HTML, and each node param in its slot as it is.
 */
export function tNodes(key, params = {}) {
    return lookupParts(key, params)
        .filter((part) => part !== "")
        .map((part) => (typeof part === "string" ? document.createTextNode(part) : part));
}

/** A key's text, or the family's generic text for a code with no key of its own, which is reported. */
export function tCode(prefix, code, genericKey, genericParams = {}) {
    const key = `${prefix}${code}`;
    if (hasKey(key)) {
        return t(key);
    }
    reportI18nError(key, "unknown code");
    return t(genericKey, genericParams);
}

export function tileVisible(code) {
    return t(`tile.visible.${code}`);
}

export function tileSpoken(code) {
    return t(`tile.spoken.${code}`);
}

/** An element's text from a key, remembered on it so that `applyStaticText` writes it again after a locale switch. */
export function setText(element, key, params = null) {
    element.setAttribute("data-i18n", key);
    if (params === null) {
        element.removeAttribute("data-i18n-params");
    } else {
        element.setAttribute("data-i18n-params", JSON.stringify(params));
    }
    element.textContent = t(key, params ?? {});
}

/** An element's attribute (`title`, `aria-label` or `alt`) from a key, remembered on it as `setText` does. */
export function setAttributeText(element, attribute, key) {
    const marker = Object.keys(STATIC_ATTRIBUTES).find(
        (name) => STATIC_ATTRIBUTES[name] === attribute,
    );
    element.setAttribute(marker, key);
    element.setAttribute(attribute, t(key));
}

function slotsOf(element) {
    const slots = {};
    for (const slot of element.querySelectorAll(":scope > [data-i18n-slot]")) {
        slots[slot.dataset.i18nSlot] = slot;
    }
    return slots;
}

function fillText(element) {
    const key = element.dataset.i18n;
    const slots = slotsOf(element);
    if (Object.keys(slots).length > 0) {
        element.replaceChildren(...tNodes(key, slots));
        return;
    }
    const params = element.dataset.i18nParams ? JSON.parse(element.dataset.i18nParams) : {};
    element.textContent = t(key, params);
}

/**
 * Write every text the markup under `root` names by key: an element's text from `data-i18n` (its `data-i18n-slot`
 * children kept as they are, in their slots, and its params from `data-i18n-params`), and its title, aria-label and alt
 * from `data-i18n-title`, `data-i18n-aria-label` and `data-i18n-alt`. Only text and those attributes change: no node is
 * replaced but a text node, so handlers, classes and focus stay. Subtrees under an element of `skip` are left as they
 * are.
 */
export function applyStaticText(root, { skip = [] } = {}) {
    const skipped = (element) => skip.some((node) => node.contains(element));
    for (const element of root.querySelectorAll("[data-i18n]")) {
        if (!skipped(element)) {
            fillText(element);
        }
    }
    for (const [marker, attribute] of Object.entries(STATIC_ATTRIBUTES)) {
        for (const element of root.querySelectorAll(`[${marker}]`)) {
            if (!skipped(element)) {
                element.setAttribute(attribute, t(element.getAttribute(marker)));
            }
        }
    }
}
