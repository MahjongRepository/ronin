import { type Router, startRouter } from "@ronin/shared/router";
import { afterEach, describe, expect, it } from "vitest";

import { type Chrome, startChrome } from "@/app/chrome";
import { type PageMeta } from "@/app/page-meta";

const META: PageMeta = { appVersion: "dev", currentYear: 2026, devMode: false, releaseUrl: "" };

function chromeOnPage(onLanguageSwitched: () => void = () => {}): {
    chrome: Chrome;
    nav: HTMLElement;
} {
    const nav = document.createElement("nav");
    const footer = document.createElement("footer");
    document.body.append(nav, footer);
    const chrome = startChrome({ footer, nav, notice: null }, META, onLanguageSwitched);
    return { chrome, nav };
}

function countingRouter(): { counts: { mounts: number; rerenders: number }; router: Router } {
    const host = document.createElement("main");
    document.body.append(host);
    const counts = { mounts: 0, rerenders: 0 };
    const router = startRouter(
        host,
        [
            {
                mount: () => {
                    counts.mounts += 1;
                    return { rerender: () => (counts.rerenders += 1), unmount: () => {} };
                },
                pattern: /^\/$/,
            },
        ],
        () => {},
    );
    return { counts, router };
}

function navHrefs(nav: HTMLElement): (string | null)[] {
    return [...nav.querySelectorAll("a")].map((link) => link.getAttribute("href"));
}

afterEach(() => {
    document.body.replaceChildren();
    document.documentElement.lang = "";
    document.cookie = "lang=; Path=/; Max-Age=0";
});

describe("startChrome", () => {
    it("links the Admin section only for an admin", () => {
        const { chrome, nav } = chromeOnPage();

        chrome.showSession({ user: { isAdmin: false, isGuest: false, username: "dev" } });
        const playerLinks = navHrefs(nav);
        chrome.showSession({ user: { isAdmin: true, isGuest: false, username: "dev" } });

        expect(playerLinks).toEqual(["/", "/history"]);
        expect(navHrefs(nav)).toEqual(["/", "/history", "/admin/monitoring"]);
        expect(nav.querySelector(".lobby-username")?.textContent).toBe("dev");
    });

    it("switches language by cookie and page lang, re-rendering the view without a remount", () => {
        const { counts, router } = countingRouter();
        chromeOnPage(() => router.rerender()).chrome.render();

        document.querySelector<HTMLButtonElement>('footer button[lang="ja"]')?.click();

        expect(document.cookie).toContain("lang=ja");
        expect(document.documentElement.lang).toBe("ja");
        expect(counts).toEqual({ mounts: 1, rerenders: 1 });
        expect(
            document.querySelector('footer button[aria-current="true"]')?.getAttribute("lang"),
        ).toBe("ja");
        expect(document.querySelector("nav")?.getAttribute("aria-label")).toBe("メイン");
    });
});
