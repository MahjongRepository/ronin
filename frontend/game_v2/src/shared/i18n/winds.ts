import { type Locale, isLocale, pageLocale } from "./locale";

export const WIND_SCRIPTS = ["latin", "kanji", "cyrillic"] as const;

export type WindScript = (typeof WIND_SCRIPTS)[number];

/** The scripts a language offers for the wind letters, its default first. */
const LOCALE_WIND_SCRIPTS: Readonly<Record<Locale, readonly [WindScript, ...WindScript[]]>> = {
    en: ["latin", "kanji"],
    ja: ["kanji", "latin"],
    ru: ["latin", "kanji", "cyrillic"],
};

/** East, South, West and North in each script; glyphs, not words, so no catalog translates them. */
export const WIND_LETTERS: Readonly<Record<WindScript, readonly string[]>> = {
    cyrillic: ["В", "Ю", "З", "С"],
    kanji: ["東", "南", "西", "北"],
    latin: ["E", "S", "W", "N"],
};

/** The language each script's letters are written in, for the `lang` of a control showing them. */
export const WIND_SCRIPT_LANGS: Readonly<Record<WindScript, Locale>> = {
    cyrillic: "ru",
    kanji: "ja",
    latin: "en",
};

export const WIND_SCRIPT_KEY = "ronin.v2.winds";

/** The script the player chose for the wind letters, and the language it was chosen in, which it lasts only for. */
export interface WindChoice {
    readonly locale: Locale;
    readonly script: WindScript;
}

function isWindScript(value: unknown): value is WindScript {
    return WIND_SCRIPTS.some((script) => script === value);
}

export function windScriptsOf(locale: Locale): readonly [WindScript, ...WindScript[]] {
    return LOCALE_WIND_SCRIPTS[locale];
}

/** The wind letters' script on the page: the one chosen in its language, else that language's default. */
export function pageWindScript(): WindScript {
    const scripts = windScriptsOf(pageLocale());
    const chosen = document.documentElement.dataset.winds;
    return scripts.find((script) => script === chosen) ?? scripts[0];
}

/** A stored choice, or null for anything else in its place. */
function readWindChoice(stored: unknown): WindChoice | null {
    if (typeof stored !== "object" || stored === null) {
        return null;
    }
    const locale = "locale" in stored ? stored.locale : undefined;
    const script = "script" in stored ? stored.script : undefined;
    if (typeof locale !== "string" || !isLocale(locale) || !isWindScript(script)) {
        return null;
    }
    return { locale, script };
}

function storeWindChoice(choice: WindChoice | null): void {
    try {
        if (choice === null) {
            localStorage.removeItem(WIND_SCRIPT_KEY);
            return;
        }
        localStorage.setItem(WIND_SCRIPT_KEY, JSON.stringify(choice));
    } catch {
        return;
    }
}

function storedWindChoice(): WindChoice | null {
    try {
        const raw = localStorage.getItem(WIND_SCRIPT_KEY);
        return raw === null ? null : readWindChoice(JSON.parse(raw));
    } catch {
        return null;
    }
}

/** Show the wind letters in `script`, kept in this browser for the page's language. */
export function applyWindScript(script: WindScript): void {
    document.documentElement.dataset.winds = script;
    storeWindChoice({ locale: pageLocale(), script });
}

/** Back to the language's default letters, forgetting the choice: a new language starts at its own default. */
export function resetWindScript(): void {
    delete document.documentElement.dataset.winds;
    storeWindChoice(null);
}

/** The page at the choice this browser kept, if it was made in the page's language. */
export function restoreWindScript(): void {
    const choice = storedWindChoice();
    if (choice !== null && choice.locale === pageLocale()) {
        document.documentElement.dataset.winds = choice.script;
    }
}
