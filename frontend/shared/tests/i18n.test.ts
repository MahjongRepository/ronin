import { I18nError, createTranslator } from "@ronin/shared/i18n";
import { html, render } from "lit-html";
import { afterEach, describe, expect, it, vi } from "vitest";

const { t, tParts } = createTranslator({
    en: {
        "test.greeting": "Hello, {name}",
        "test.reload": "Reload",
        "test.score": "{points} points",
        "test.tiles": { one: "{count} tile", other: "{count} tiles" },
        "test.waiting_for": "Waiting for {names} to get ready.",
    },
    ja: {
        "test.greeting": "こんにちは、{name}",
        "test.reload": "再読み込み",
        "test.score": "{points}点",
        "test.tiles": { other: "{count}枚" },
        "test.waiting_for": "{names}の準備を待っています。",
    },
    ru: {
        "test.greeting": "Привет, {name}",
        "test.score": "{points} очков",
        "test.tiles": {
            few: "{count} тайла",
            many: "{count} тайлов",
            one: "{count} тайл",
            other: "{count} тайла",
        },
        "test.waiting_for": "Ждём, пока {names} будут готовы.",
    },
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    document.documentElement.lang = "";
    document.body.replaceChildren();
});

describe("createTranslator", () => {
    it("fills params, formats numbers and picks a plural form by the page language's rules", () => {
        document.documentElement.lang = "ru";

        expect(t("test.greeting", { name: "dev" })).toBe("Привет, dev");
        expect(t("test.score", { points: 12_000 })).toBe("12 000 очков");
        expect([1, 3, 5, 21].map((count) => t("test.tiles", { count }))).toEqual([
            "1 тайл",
            "3 тайла",
            "5 тайлов",
            "21 тайл",
        ]);
    });

    it("throws in development on a key missing from the catalog or the page language, or a param the message does not take", () => {
        // @ts-expect-error -- "test.no_such_key" is not a key of the en catalog
        expect(() => t("test.no_such_key")).toThrow(I18nError);
        expect(() => t("test.greeting")).toThrow(I18nError);
        expect(() => t("test.reload", { name: "dev" })).toThrow(I18nError);
        expect(() => t("test.reload", { count: 4 })).toThrow(I18nError);
        expect(() => t("test.tiles", { count: "4" })).toThrow(I18nError);
        document.documentElement.lang = "ru";
        expect(() => t("test.reload")).toThrow(/missing ru translation/);
    });

    it("shows English for a key the page language lacks in production, reported once", () => {
        vi.stubEnv("DEV", false);
        document.documentElement.lang = "ru";
        const report = vi.spyOn(console, "error").mockImplementation(() => {});

        expect(t("test.reload")).toBe("Reload");
        expect(t("test.reload")).toBe("Reload");

        expect(report).toHaveBeenCalledExactlyOnceWith("i18n error", {
            key: "test.reload",
            locale: "ru",
            reason: "missing ru translation",
        });
    });
});

describe("tParts", () => {
    it("renders a template param in its slot and keeps a translated string as text", () => {
        const container = document.createElement("div");
        const link = html`
            <a href="/rooms/1">Jade Crane</a>
        `;

        render(html`${tParts("test.waiting_for", { names: link })}`, container);
        render(html`${tParts("test.waiting_for", { names: "<b>dev</b>" })}`, document.body);

        expect(container.querySelector("a")?.textContent).toBe("Jade Crane");
        expect(container.textContent?.replace(/\s+/g, " ")).toBe(
            "Waiting for Jade Crane to get ready.",
        );
        expect(document.body.querySelector("b")).toBeNull();
        expect(document.body.textContent).toContain("<b>dev</b>");
    });
});
