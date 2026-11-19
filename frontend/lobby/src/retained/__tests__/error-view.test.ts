import { afterEach, describe, expect, it, vi } from "vitest";

import { startRetainedPage } from "@/app/start";

const PAGE_META = `
    <meta name="csrf-token" content="token">
    <meta name="ronin-app-version" content="dev">
    <meta name="ronin-release-url" content="">
    <meta name="ronin-current-year" content="2026">
    <meta name="ronin-dev-mode" content="false">
    <meta name="ronin-error-status" content="403">
    <meta name="ronin-error-code" content="session_expired">
    <meta name="ronin-error-action" content="/history">`;

function errorPage(): HTMLElement {
    document.documentElement.lang = "en";
    document.head.innerHTML = PAGE_META;
    document.body.innerHTML = `<nav data-lobby-nav></nav>
        <main><div data-browser-notice hidden></div><section data-error-view></section></main>
        <footer data-lobby-footer></footer>`;
    vi.stubGlobal(
        "fetch",
        vi.fn(() => Promise.resolve(Response.json({ user: null }))),
    );
    const host = document.querySelector<HTMLElement>("[data-error-view]");
    if (host === null) {
        throw new Error("missing error mount");
    }
    return host;
}

function shownError(host: HTMLElement): { hrefs: (string | null)[]; title: string | undefined } {
    return {
        hrefs: [...host.querySelectorAll("a")].map((link) => link.getAttribute("href")),
        title: host.querySelector("h1")?.textContent,
    };
}

afterEach(() => {
    vi.unstubAllGlobals();
    document.head.replaceChildren();
    document.body.replaceChildren();
    document.documentElement.lang = "";
});

describe("error view", () => {
    it("renders the error from its code and re-renders it in place in the language switched to", () => {
        const host = errorPage();

        startRetainedPage();
        const english = shownError(host);
        document.querySelector<HTMLButtonElement>('footer button[lang="ja"]')?.click();

        expect(english).toEqual({ hrefs: ["/history", "/"], title: "Session expired" });
        expect(host.querySelector(".lobby-error-code")?.textContent).toBe("403");
        expect(shownError(host).title).toBe("セッション切れ");
        expect(host.querySelector('a[href="/history"]')?.textContent).toBe("ページを再読み込み");
        expect(document.title).toBe("セッション切れ · Ronin Beta");
    });
});
