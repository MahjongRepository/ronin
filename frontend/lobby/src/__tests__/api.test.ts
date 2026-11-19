import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet, apiPost } from "@/api";

function jsonResponse(status: number, body: unknown): Response {
    return Response.json(body, { status });
}

function setMetaToken(token: string): void {
    const meta = document.createElement("meta");
    meta.name = "csrf-token";
    meta.content = token;
    document.head.append(meta);
}

function sentCsrfTokens(fetchMock: ReturnType<typeof vi.fn>): unknown[] {
    return fetchMock.mock.calls.map(([, init]) => {
        const { headers } = init as RequestInit;
        return (headers as Record<string, string>)["X-CSRF-Token"];
    });
}

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    document.head.replaceChildren();
    history.replaceState(null, "", "/");
});

describe("apiPost", () => {
    it("retries once with the fresh token a csrf_invalid answer carries", async () => {
        setMetaToken("stale");
        const fetchMock = vi
            .fn()
            .mockResolvedValueOnce(
                jsonResponse(403, { csrf_token: "fresh", error: "csrf_invalid" }),
            )
            .mockResolvedValueOnce(jsonResponse(201, { room_id: "r1" }));
        vi.stubGlobal("fetch", fetchMock);

        const result = await apiPost("/api/lobby/rooms", {});

        expect(result).toEqual({ data: { room_id: "r1" }, ok: true });
        expect(sentCsrfTokens(fetchMock)).toEqual(["stale", "fresh"]);
    });
});

describe("apiGet", () => {
    it("sends a 401 to the login page with the current path and query as next", async () => {
        history.replaceState(null, "", "/history?page=2");
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(401, { error: "x" })));
        const assign = vi.spyOn(window.location, "assign").mockImplementation(() => {});

        const result = await apiGet("/api/lobby/rooms");

        expect(result).toEqual({ error: "unauthorized", ok: false });
        expect(assign).toHaveBeenCalledExactlyOnceWith("/login?next=%2Fhistory%3Fpage%3D2");
    });
});
