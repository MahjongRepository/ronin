import { getGameSession, storeGameSession } from "@ronin/shared/session-storage";
import { afterEach, describe, expect, it, vi } from "vitest";

import { submitCredentials } from "@/auth/handlers";
import { type AuthPage, createAuthState } from "@/auth/state";
import { renderAuth } from "@/auth/ui";
import { t } from "@/i18n";

function setMetaToken(token: string): void {
    const meta = document.createElement("meta");
    meta.name = "csrf-token";
    meta.content = token;
    document.head.append(meta);
}

function mockFetch(...answers: { body: unknown; status: number }[]): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn();
    for (const { body, status } of answers) {
        fetchMock.mockResolvedValueOnce(Response.json(body, { status }));
    }
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

function sentRequests(fetchMock: ReturnType<typeof vi.fn>): { body: unknown; token: unknown }[] {
    return fetchMock.mock.calls.map(([, init]) => {
        const { body, headers } = init as RequestInit;
        return {
            body: JSON.parse(String(body)) as unknown,
            token: (headers as Record<string, string>)["X-CSRF-Token"],
        };
    });
}

function setUpForm(page: AuthPage) {
    const host = document.createElement("main");
    document.body.append(host);
    const state = createAuthState(page, new URL("http://localhost/login?next=%2Fhistory"));
    const actions = { startGuest: () => {}, submit: () => {} };
    function render(): void {
        renderAuth(host, state, actions);
    }
    render();
    return { context: { isDisposed: () => false, render, showError: render }, host, state };
}

function alertText(host: HTMLElement): string | undefined {
    return host.querySelector("[role=alert]")?.textContent?.trim();
}

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionStorage.clear();
    document.head.replaceChildren();
    document.body.replaceChildren();
});

describe("submitCredentials", () => {
    it("retries a stale token once and keeps the typed username on the failure that follows", async () => {
        setMetaToken("stale");
        const fetchMock = mockFetch(
            { body: { csrf_token: "fresh", error: "csrf_invalid" }, status: 403 },
            {
                body: { code: "wrong_credentials", error: "auth_error", field: null, params: {} },
                status: 400,
            },
        );
        const { context, host, state } = setUpForm("login");

        await submitCredentials(state, context, {
            confirmPassword: null,
            password: "wrong-password",
            username: "dev",
        });

        const credentials = { next: "/history", password: "wrong-password", username: "dev" };
        expect(sentRequests(fetchMock)).toEqual([
            { body: credentials, token: "stale" },
            { body: credentials, token: "fresh" },
        ]);
        expect(host.querySelector<HTMLInputElement>("#username")?.value).toBe("dev");
        expect(alertText(host)).toBe(t("auth.error.wrong_credentials"));
    });

    it("shows an auth_error by its translated code and params and marks its field", async () => {
        setMetaToken("token");
        mockFetch({
            body: {
                code: "username_taken",
                error: "auth_error",
                field: "username",
                params: { username: "dev" },
            },
            status: 400,
        });
        const { context, host, state } = setUpForm("register");

        await submitCredentials(state, context, {
            confirmPassword: "secret-password",
            password: "secret-password",
            username: "dev",
        });

        expect(alertText(host)).toBe(t("auth.error.username_taken", { username: "dev" }));
        expect(host.querySelector("#username")?.getAttribute("aria-invalid")).toBe("true");
        expect(host.querySelector("#password")?.hasAttribute("aria-invalid")).toBe(false);
    });

    it("forgets every game handoff of the tab before opening the signed-in page", async () => {
        setMetaToken("token");
        mockFetch({ body: { next: "/history" }, status: 200 });
        const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
        storeGameSession("game-1", "ws://game", "ticket-of-previous-account");
        const { context, state } = setUpForm("login");

        await submitCredentials(state, context, {
            confirmPassword: null,
            password: "secret-password",
            username: "dev",
        });

        expect(getGameSession("game-1")).toBeNull();
        expect(replace).toHaveBeenCalledWith("/history");
    });
});
