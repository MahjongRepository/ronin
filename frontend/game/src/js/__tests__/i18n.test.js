import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LOCALE_SCRIPT from "../../../public/locale.js?raw";
import {
    I18nError,
    applyStaticText,
    setLocale,
    t,
    tNodes,
    writeLangCookie,
} from "../../i18n/index.js";

function clearCookies() {
    for (const entry of document.cookie.split(";")) {
        const name = entry.split("=")[0].trim();
        if (name) {
            document.cookie = `${name}=; Path=/; Max-Age=0`;
        }
    }
}

function resolvedLocale({ cookie = null, languages = [] }) {
    clearCookies();
    if (cookie !== null) {
        document.cookie = `lang=${cookie}; Path=/`;
    }
    vi.spyOn(navigator, "languages", "get").mockReturnValue(languages);
    document.documentElement.removeAttribute("lang");
    new Function(LOCALE_SCRIPT)();
    return document.documentElement.lang;
}

afterEach(() => {
    vi.restoreAllMocks();
    clearCookies();
});

describe("public/locale.js", () => {
    it("takes a supported lang cookie over the browser's languages", () => {
        expect(resolvedLocale({ cookie: "ja", languages: ["ru-RU", "en"] })).toBe("ja");
    });

    it("takes the first browser language it supports, by its primary subtag", () => {
        expect(resolvedLocale({ languages: ["ru-RU", "en"] })).toBe("ru");
        expect(resolvedLocale({ languages: ["fr-FR", "JA"] })).toBe("ja");
    });

    it("ignores a lang cookie outside the supported locales", () => {
        expect(resolvedLocale({ cookie: "de", languages: ["ja-JP"] })).toBe("ja");
    });

    it("falls back to English", () => {
        expect(resolvedLocale({ cookie: "xx", languages: ["fr-FR", "de"] })).toBe("en");
    });
});

describe("writeLangCookie", () => {
    it("writes the cookie the page's next load resolves", () => {
        writeLangCookie("ru");
        vi.spyOn(navigator, "languages", "get").mockReturnValue(["ja-JP"]);
        document.documentElement.removeAttribute("lang");

        new Function(LOCALE_SCRIPT)();

        expect(document.documentElement.lang).toBe("ru");
    });
});

describe("applyStaticText", () => {
    beforeEach(() => setLocale("ru"));

    it("fills text, title, aria-label and alt, keeping slot children as they are", () => {
        document.body.innerHTML = `
            <button class="skip" data-i18n="game.call.pon" data-i18n-title="game.button.skip"
                data-i18n-aria-label="game.button.skip">Pon</button>
            <img class="tile" data-i18n-alt="tile.spoken.z7" alt="">
            <div class="wall" data-i18n="game.board.wall">Tiles left: <span class="paishu" data-i18n-slot="tiles">66</span></div>`;
        const count = document.querySelector(".paishu");

        applyStaticText(document);

        const button = document.querySelector(".skip");
        expect(button.textContent).toBe("Пон");
        expect(button.title).toBe("Пропустить");
        expect(button.getAttribute("aria-label")).toBe("Пропустить");
        expect(document.querySelector(".tile").alt).toBe("красный дракон");
        expect(document.querySelector(".wall").textContent).toBe("В стене: 66");
        expect(document.querySelector(".paishu")).toBe(count);
    });

    it("leaves the subtrees it is told to skip", () => {
        document.body.innerHTML = `<div class="dialog"><span data-i18n="game.result.next">次へ</span></div>`;

        applyStaticText(document, { skip: [document.querySelector(".dialog")] });

        expect(document.querySelector(".dialog span").textContent).toBe("次へ");
    });
});

describe("t and tNodes", () => {
    beforeEach(() => setLocale("en"));

    it("makes text nodes of a param holding markup, never elements", () => {
        const nodes = tNodes("game.board.kyotaku", { sticks: "<b>3</b>" });

        expect(nodes.every((node) => node.nodeType === Node.TEXT_NODE)).toBe(true);
        expect(nodes.map((node) => node.textContent).join("")).toBe("Sticks: <b>3</b>");
    });

    it("throws in strict mode on a missing key, a missing param and an extra param", () => {
        expect(() => t("game.no_such_key")).toThrow(I18nError);
        expect(() => t("game.board.kyotaku")).toThrow(/missing params sticks/);
        expect(() => t("game.call.pon", { name: "Alice" })).toThrow(/unexpected params name/);
    });
});
