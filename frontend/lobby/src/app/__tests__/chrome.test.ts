import { type Router, startRouter } from "@ronin/shared/router";
import { getGameSession, storeGameSession } from "@ronin/shared/session-storage";
import { afterEach, describe, expect, it } from "vitest";

import { type Chrome, startChrome } from "@/app/chrome";
import { type PageMeta } from "@/app/page-meta";

const META: PageMeta = { appVersion: "dev", currentYear: 2026, devMode: false, releaseUrl: "" };

function chromeOnPage(onLanguageSwitched: () => void = () => {}): {
    chrome: Chrome;
    nav: HTMLElement;
} {
    const csrfToken = document.createElement("meta");
    csrfToken.name = "csrf-token";
    csrfToken.content = "first-token";
    document.head.append(csrfToken);
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

function postedTokenAfterRotation(nav: HTMLElement, rotatedToken: string): string | undefined {
    document.querySelector('meta[name="csrf-token"]')?.setAttribute("content", rotatedToken);
    const form = nav.querySelector<HTMLFormElement>('form[action="/logout"]');
    document.addEventListener("submit", (event) => event.preventDefault(), { once: true });
    form?.requestSubmit();
    return form?.querySelector<HTMLInputElement>('input[name="csrf_token"]')?.value;
}

function clickLanguage(locale: string): void {
    document.querySelector<HTMLButtonElement>(`footer button[lang="${locale}"]`)?.click();
}

function navHrefs(nav: HTMLElement): (string | null)[] {
    return [...nav.querySelectorAll("a")].map((link) => link.getAttribute("href"));
}

function openAccountMenu(nav: HTMLElement): { expanded: string | null; items: string[] } {
    const toggle = nav.querySelector<HTMLButtonElement>(".lobby-account-toggle");
    toggle?.click();
    const panel = nav.querySelector<HTMLElement>(".lobby-account-panel:not([hidden])");
    return {
        expanded: toggle?.getAttribute("aria-expanded") ?? null,
        items: [...(panel?.querySelectorAll(".lobby-account-item") ?? [])].map(
            (item) => item.textContent?.trim() ?? "",
        ),
    };
}

function pressEscapeInAccountPanel(nav: HTMLElement): void {
    const settings = nav.querySelector<HTMLAnchorElement>(".lobby-account-panel a");
    settings?.focus();
    settings?.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Escape" }));
}

afterEach(() => {
    sessionStorage.clear();
    document.body.replaceChildren();
    document.head.replaceChildren();
    document.documentElement.lang = "";
    delete document.documentElement.dataset.winds;
    document.cookie = "lang=; Path=/; Max-Age=0";
});

describe("startChrome", () => {
    it("links Tournaments for everyone, the Admin section only for an admin and logs out with the current token", () => {
        const { chrome, nav } = chromeOnPage();

        chrome.showSession({ user: { isAdmin: false, isGuest: false, username: "dev" } });
        const playerLinks = navHrefs(nav);
        chrome.showSession({ user: { isAdmin: true, isGuest: false, username: "dev" } });
        const postedToken = postedTokenAfterRotation(nav, "rotated-token");

        expect(playerLinks).toEqual(["/", "/history", "/tournaments", "/tournaments", "/settings"]);
        expect(navHrefs(nav)).toEqual([
            "/",
            "/history",
            "/tournaments",
            "/admin/monitoring",
            "/tournaments",
            "/admin/monitoring",
            "/settings",
        ]);
        expect(nav.querySelector(".lobby-username")?.textContent).toBe("dev");
        expect(postedToken).toBe("rotated-token");
    });

    it("marks Tournaments current on a tournament's page as well as on the list", () => {
        window.history.replaceState(null, "", "/tournaments/cup");
        const { chrome, nav } = chromeOnPage();

        chrome.showSession({ user: { isAdmin: false, isGuest: false, username: "dev" } });
        const onTournament = [...nav.querySelectorAll('a[href="/tournaments"]')].map((link) =>
            link.getAttribute("aria-current"),
        );
        window.history.replaceState(null, "", "/tournaments-archive");
        chrome.showSession({ user: { isAdmin: false, isGuest: false, username: "dev" } });

        expect(onTournament).toEqual(["true", "true"]);
        expect(
            nav.querySelector('a[href="/tournaments"]')?.getAttribute("aria-current"),
        ).toBeNull();
        window.history.replaceState(null, "", "/");
    });

    it("forgets every game handoff of the tab on logout", () => {
        const { chrome, nav } = chromeOnPage();
        chrome.showSession({ user: { isAdmin: false, isGuest: false, username: "dev" } });
        storeGameSession("game-1", "ws://game", "ticket-of-dev");

        postedTokenAfterRotation(nav, "first-token");

        expect(getGameSession("game-1")).toBeNull();
    });

    it("opens the account panel with Tournaments, Settings and Log out, and Escape closes it onto its button", () => {
        const { chrome, nav } = chromeOnPage();
        chrome.showSession({ user: { isAdmin: false, isGuest: true, username: "Nanashi-1234" } });
        const toggle = nav.querySelector<HTMLButtonElement>(".lobby-account-toggle");

        const opened = openAccountMenu(nav);
        pressEscapeInAccountPanel(nav);

        expect(toggle?.getAttribute("aria-label")).toBe("Nanashi-1234, account menu");
        expect(opened).toEqual({
            expanded: "true",
            items: ["Tournaments", "Game settings", "Log out"],
        });
        expect(nav.querySelector<HTMLElement>(".lobby-account-panel")?.hidden).toBe(true);
        expect(toggle?.getAttribute("aria-expanded")).toBe("false");
        expect(document.activeElement).toBe(toggle);
    });

    it("switches language by cookie and page lang, re-rendering the view without a remount, once", () => {
        const { counts, router } = countingRouter();
        chromeOnPage(() => router.rerender()).chrome.render();

        clickLanguage("ja");
        document.documentElement.dataset.winds = "kanji";
        clickLanguage("ja");

        expect(document.cookie).toContain("lang=ja");
        expect(document.documentElement.lang).toBe("ja");
        expect({ ...counts, winds: document.documentElement.dataset.winds }).toEqual({
            mounts: 1,
            rerenders: 1,
            winds: "kanji",
        });
        expect(
            document.querySelector('footer button[aria-current="true"]')?.getAttribute("lang"),
        ).toBe("ja");
        expect(document.querySelector("nav")?.getAttribute("aria-label")).toBe("メイン");
    });
});
