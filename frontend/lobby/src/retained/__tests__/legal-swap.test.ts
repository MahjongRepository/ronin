import { afterEach, describe, expect, it, vi } from "vitest";

import { startRetainedPage } from "@/app/start";

const PAGE_META = `
    <meta name="csrf-token" content="token">
    <meta name="ronin-app-version" content="dev">
    <meta name="ronin-release-url" content="">
    <meta name="ronin-current-year" content="2026">
    <meta name="ronin-dev-mode" content="false">`;

const JAPANESE_TERMS = `<!DOCTYPE html><html lang="ja"><head><meta name="csrf-token" content="reissued-token"><title>利用規約 · Ronin Beta</title></head><body>
    <nav data-lobby-nav></nav>
    <main><div data-browser-notice hidden></div><article class="lobby-legal"><h1>利用規約</h1></article></main>
    <footer data-lobby-footer></footer></body></html>`;

function answer(path: string): Promise<Response> {
    if (path === "/api/lobby/session") {
        return Promise.resolve(Response.json({ user: null }));
    }
    return Promise.resolve(
        new Response(JAPANESE_TERMS, { headers: { "Content-Type": "text/html" } }),
    );
}

function englishTermsPage(): Element | null {
    history.replaceState(null, "", "/terms");
    document.documentElement.lang = "en";
    document.head.innerHTML = PAGE_META;
    document.title = "Terms of Service · Ronin Beta";
    document.body.innerHTML = `<nav data-lobby-nav></nav>
        <main><div data-browser-notice hidden></div><article class="lobby-legal"><h1>Terms of Service</h1></article></main>
        <footer data-lobby-footer></footer>`;
    return document.querySelector("[data-browser-notice]");
}

afterEach(() => {
    vi.unstubAllGlobals();
    document.head.replaceChildren();
    document.body.replaceChildren();
    document.documentElement.lang = "";
    history.replaceState(null, "", "/");
});

describe("legal swap", () => {
    it("replaces the page content, title and CSRF token with the refetched page's, keeping the notice", async () => {
        const notice = englishTermsPage();
        const fetchPage = vi.fn(answer);
        vi.stubGlobal("fetch", fetchPage);

        startRetainedPage();
        document.querySelector<HTMLButtonElement>('footer button[lang="ja"]')?.click();

        await vi.waitFor(() => {
            expect(document.querySelector("main h1")?.textContent).toBe("利用規約");
        });
        expect({
            csrfToken: document.querySelector('meta[name="csrf-token"]')?.getAttribute("content"),
            title: document.title,
        }).toEqual({ csrfToken: "reissued-token", title: "利用規約 · Ronin Beta" });
        expect(document.querySelectorAll("main article")).toHaveLength(1);
        expect(document.querySelector("main")?.firstElementChild).toBe(notice);
        expect(fetchPage).toHaveBeenCalledWith(window.location.href, expect.anything());
    });
});
