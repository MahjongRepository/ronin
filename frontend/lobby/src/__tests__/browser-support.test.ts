import { afterEach, describe, expect, it } from "vitest";

import { showUnsupportedBrowserNotice } from "@/browser-support";

function registerProperty(): void {}

function renderNotice(): HTMLElement {
    document.body.innerHTML = `<div data-browser-notice hidden></div>`;
    return document.querySelector<HTMLElement>("[data-browser-notice]")!;
}

describe("showUnsupportedBrowserNotice", () => {
    afterEach(() => {
        document.body.innerHTML = "";
    });

    it("keeps the notice hidden in a browser with every CSS feature the game board needs", () => {
        const notice = renderNotice();

        showUnsupportedBrowserNotice({ registerProperty, supports: () => true });

        expect(notice.hidden).toBe(true);
    });

    it("shows the notice in a browser missing :has() or @property, as Firefox before 121 and 128", () => {
        const withoutHas = renderNotice();
        showUnsupportedBrowserNotice({
            registerProperty,
            supports: (condition) => !condition.includes(":has("),
        });
        const withoutRegisteredProperties = renderNotice();
        showUnsupportedBrowserNotice({ supports: () => true });

        expect([withoutHas.hidden, withoutRegisteredProperties.hidden]).toEqual([false, false]);
    });
});
