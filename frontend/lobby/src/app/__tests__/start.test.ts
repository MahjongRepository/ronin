import { afterEach, describe, expect, it, vi } from "vitest";

import { startLobbyApp } from "@/app/start";

const SHELL_META = `
    <meta name="csrf-token" content="token">
    <meta name="ronin-app-version" content="dev">
    <meta name="ronin-release-url" content="">
    <meta name="ronin-current-year" content="2026">
    <meta name="ronin-dev-mode" content="false">`;

function shellHost(): HTMLElement {
    document.head.innerHTML = SHELL_META;
    document.body.innerHTML = `<nav data-lobby-nav></nav><main id="lobby-spa"></main><footer data-lobby-footer></footer>`;
    const host = document.getElementById("lobby-spa");
    if (host === null) {
        throw new Error("missing #lobby-spa");
    }
    return host;
}

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    document.head.replaceChildren();
    document.body.replaceChildren();
    history.replaceState(null, "", "/");
});

describe("startLobbyApp", () => {
    it("shows the page as failed instead of reloading when the first URL matches no route", () => {
        const host = shellHost();
        history.replaceState(null, "", "/rooms/%ZZ");
        vi.stubGlobal(
            "fetch",
            vi.fn(() => new Promise<Response>(() => {})),
        );
        const reload = vi.spyOn(window.location, "reload").mockImplementation(() => {});

        startLobbyApp(host);

        expect(reload).not.toHaveBeenCalled();
        expect(host.querySelector(".lobby-alert")?.textContent).toBe("This page failed to load.");
    });
});
