import { describe, expect, it } from "vitest";

import { langCookie, resolveLocale } from "@/shared/i18n";

describe("resolveLocale", () => {
    it("takes a lang cookie naming a supported locale over the browser's languages", () => {
        expect(resolveLocale("session=abc; lang=ja; theme=dark", ["ru-RU", "en"])).toBe("ja");
    });

    it("falls back to the browser's languages for a lang cookie that is not exactly a supported code", () => {
        expect(resolveLocale("lang=ja-JP", ["ru"])).toBe("ru");
        expect(resolveLocale("lang=fr", ["ru"])).toBe("ru");
    });

    it("matches a browser language by its primary subtag case-insensitively, skipping the wildcard", () => {
        expect(resolveLocale("", ["*", "de-DE", "RU-ru", "ja"])).toBe("ru");
    });

    it("gives English when neither the cookie nor the browser names a supported locale", () => {
        expect(resolveLocale("lang=fr", ["de", "*"])).toBe("en");
    });
});

describe("langCookie", () => {
    it("carries the lobby's lang cookie attributes, marked Secure only on https", () => {
        expect(langCookie("ru", "http:")).toBe("lang=ru; Path=/; Max-Age=31536000; SameSite=Lax");
        expect(langCookie("ja", "https:")).toBe(
            "lang=ja; Path=/; Max-Age=31536000; SameSite=Lax; Secure",
        );
    });
});
