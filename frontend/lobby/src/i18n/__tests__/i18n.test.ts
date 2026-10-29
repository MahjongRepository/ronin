import { html, render } from "lit-html";
import { afterEach, describe, expect, test, vi } from "vitest";

import { I18nError, t, tParts } from "@/i18n";

const { UNTRANSLATED_KEY } = vi.hoisted(() => ({ UNTRANSLATED_KEY: "common.reload" }) as const);

vi.mock("@/i18n/locales/ru.json", async (importOriginal) => {
    const original: { default: Record<string, unknown> } = await importOriginal();
    return {
        default: Object.fromEntries(
            Object.entries(original.default).filter(([key]) => key !== UNTRANSLATED_KEY),
        ),
    };
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    document.documentElement.lang = "";
    document.body.replaceChildren();
});

describe("t", () => {
    test("reads the page language from <html lang> and falls back to English for any other value", () => {
        document.documentElement.lang = "ja";
        expect(t("room.start")).toBe("対局開始");

        document.documentElement.lang = "ja-JP";
        expect(t("room.start")).toBe("Start game");
    });

    test("throws in development on a key missing from the catalog or the page language, or a param the message does not take", () => {
        // @ts-expect-error -- "room.no_such_key" is not a key of the en catalog
        expect(() => t("room.no_such_key")).toThrow(I18nError);
        expect(() => t("room.chat.player_joined")).toThrow(I18nError);
        expect(() => t("room.start", { name: "dev" })).toThrow(I18nError);
        expect(() => t("matchmaking.hint", { count: "4" })).toThrow(I18nError);
        document.documentElement.lang = "ru";
        expect(() => t(UNTRANSLATED_KEY)).toThrow(/missing ru translation/);
    });

    test("shows English for a key the page language lacks in production, reported once", () => {
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
});

describe("tParts", () => {
    test("renders a template param in its slot and keeps a translated string as text", () => {
        const container = document.createElement("div");
        const link = html`
            <a href="/rooms/1">Jade Crane</a>
        `;

        render(html`${tParts("room.waiting_for", { names: link })}`, container);
        render(html`${tParts("room.waiting_for", { names: "<b>dev</b>" })}`, document.body);

        expect(container.querySelector("a")?.textContent).toBe("Jade Crane");
        expect(container.textContent?.replace(/\s+/g, " ")).toBe(
            "Waiting for Jade Crane to get ready.",
        );
        expect(document.body.querySelector("b")).toBeNull();
        expect(document.body.textContent).toContain("<b>dev</b>");
    });
});
