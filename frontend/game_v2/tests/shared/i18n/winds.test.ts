import { afterEach, describe, expect, it } from "vitest";

import { resetPageLanguage } from "#tests/fixtures/language";
import {
    WIND_SCRIPT_KEY,
    applyPageLocale,
    applyWindScript,
    pageWindScript,
    restoreWindScript,
    windScriptsOf,
} from "@/shared/i18n";

afterEach(() => {
    resetPageLanguage();
    delete document.documentElement.dataset.winds;
    localStorage.removeItem(WIND_SCRIPT_KEY);
});

describe("pageWindScript", () => {
    it("offers each language its own scripts, its default first", () => {
        expect([windScriptsOf("ja"), windScriptsOf("en"), windScriptsOf("ru")]).toEqual([
            ["kanji", "latin"],
            ["latin", "kanji"],
            ["latin", "kanji", "cyrillic"],
        ]);
    });

    it("falls back to the language's default for a script the language does not offer", () => {
        document.documentElement.lang = "en";
        document.documentElement.dataset.winds = "cyrillic";

        expect(pageWindScript()).toBe("latin");
    });

    it("drops the chosen script for the new language's default when the language switches", () => {
        document.documentElement.lang = "ru";
        applyWindScript("kanji");
        const chosen = pageWindScript();

        applyPageLocale("en");
        const switched = pageWindScript();
        applyPageLocale("ru");

        expect([chosen, switched, pageWindScript(), localStorage.getItem(WIND_SCRIPT_KEY)]).toEqual(
            ["kanji", "latin", "latin", null],
        );
    });
});

describe("restoreWindScript", () => {
    it("restores a choice made in the page's language and ignores one made in another", () => {
        document.documentElement.lang = "ru";
        applyWindScript("cyrillic");
        delete document.documentElement.dataset.winds;

        restoreWindScript();
        const sameLanguage = pageWindScript();
        delete document.documentElement.dataset.winds;
        document.documentElement.lang = "ja";
        restoreWindScript();

        expect([sameLanguage, pageWindScript()]).toEqual(["cyrillic", "kanji"]);
    });
});
