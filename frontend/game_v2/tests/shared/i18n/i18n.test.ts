import { afterEach, describe, expect, it, vi } from "vitest";

import { I18nError, type MessageKey, isMessageKey, t } from "@/shared/i18n";

const { PLURAL_KEY, UNTRANSLATED_KEY } = vi.hoisted(
    () => ({ PLURAL_KEY: "test.tiles", UNTRANSLATED_KEY: "common.reload" }) as const,
);

vi.mock("@/shared/i18n/locales/en.json", async (importOriginal) => {
    const original: { default: Record<string, unknown> } = await importOriginal();
    return {
        default: {
            ...original.default,
            [PLURAL_KEY]: { one: "{count} tile", other: "{count} tiles" },
        },
    };
});

vi.mock("@/shared/i18n/locales/ru.json", async (importOriginal) => {
    const original: { default: Record<string, unknown> } = await importOriginal();
    return {
        default: {
            ...Object.fromEntries(
                Object.entries(original.default).filter(([key]) => key !== UNTRANSLATED_KEY),
            ),
            [PLURAL_KEY]: {
                few: "{count} тайла",
                many: "{count} тайлов",
                one: "{count} тайл",
                other: "{count} тайла",
            },
        },
    };
});

function pluralKey(): MessageKey {
    if (!isMessageKey(PLURAL_KEY)) {
        throw new Error(`${PLURAL_KEY} is not in the mocked catalog`);
    }
    return PLURAL_KEY;
}

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    document.documentElement.lang = "";
});

describe("t", () => {
    it("reads the page language from <html lang> and falls back to English for any other value", () => {
        document.documentElement.lang = "ja";
        expect(t("common.lobby")).toBe("ロビー");

        document.documentElement.lang = "ja-JP";
        expect(t("common.lobby")).toBe("Lobby");
    });

    it("throws in development on a key missing from the catalog or the page language, or a param the message does not take", () => {
        // @ts-expect-error -- "game.no_such_key" is not a key of the en catalog
        expect(() => t("game.no_such_key")).toThrow(I18nError);
        expect(() => t("common.lobby", { name: "dev" })).toThrow(I18nError);
        expect(() => t("common.lobby", { count: 4 })).toThrow(I18nError);
        expect(() => t(pluralKey())).toThrow(I18nError);
        document.documentElement.lang = "ru";
        expect(() => t(UNTRANSLATED_KEY)).toThrow(/missing ru translation/);
    });

    it("shows English for a key the page language lacks in production, reported once", () => {
        vi.stubEnv("DEV", false);
        document.documentElement.lang = "ru";
        const report = vi.spyOn(console, "error").mockImplementation(() => {});

        expect(t(UNTRANSLATED_KEY)).toBe("Reload");
        expect(t(UNTRANSLATED_KEY)).toBe("Reload");

        expect(report).toHaveBeenCalledExactlyOnceWith("i18n error", {
            key: UNTRANSLATED_KEY,
            locale: "ru",
            reason: "missing ru translation",
        });
    });

    it("picks a plural form by the page language's rules for the count", () => {
        document.documentElement.lang = "ru";

        expect([1, 3, 5, 21].map((count) => t(pluralKey(), { count }))).toEqual([
            "1 тайл",
            "3 тайла",
            "5 тайлов",
            "21 тайл",
        ]);
    });
});
