import { startRouter } from "@ronin/shared/router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { lobbyRoutes } from "@/app/routes";

function signedOutFetch(path: string): Promise<Response> {
    if (path === "/api/lobby/session") {
        return Promise.resolve(Response.json({ user: null }));
    }
    return new Promise<Response>(() => {});
}

afterEach(() => {
    vi.unstubAllGlobals();
    document.body.replaceChildren();
    history.replaceState(null, "", "/");
});

describe("lobbyRoutes", () => {
    it("sends a signed-out internal navigation to settings to the login page with settings as next", async () => {
        vi.stubGlobal("fetch", vi.fn(signedOutFetch));
        history.replaceState(null, "", "/history");
        const host = document.createElement("main");
        document.body.append(host);
        const router = startRouter(
            host,
            lobbyRoutes({
                navigate: (url, options) => router.navigate(url, options),
                setLanguage: () => {},
            }),
            () => {},
        );

        router.navigate("/settings");

        await vi.waitFor(() => {
            expect(window.location.pathname + window.location.search).toBe(
                "/login?next=%2Fsettings",
            );
        });
    });
});
