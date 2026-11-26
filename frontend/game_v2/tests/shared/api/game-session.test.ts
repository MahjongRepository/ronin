import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchGameHandoff } from "@/shared/api";

function answer(status: number, body: unknown): void {
    vi.stubGlobal(
        "fetch",
        vi.fn(() => Promise.resolve(Response.json(body, { status }))),
    );
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("fetchGameHandoff", () => {
    it("reads the lobby's handoff into the game, its client's URL and a new claim on the seat to join with", async () => {
        answer(200, {
            game_client_url: "/play",
            game_id: "g2",
            game_ticket: "ticket-2",
            seat_version: 3,
            ws_url: "ws://game/ws/g2",
        });

        await expect(fetchGameHandoff(new AbortController().signal)).resolves.toEqual({
            gameClientUrl: "/play",
            gameId: "g2",
            handoff: {
                claimId: expect.stringMatching(/^[0-9a-f]{32}$/u),
                gameTicket: "ticket-2",
                seatVersion: 3,
                wsUrl: "ws://game/ws/g2",
            },
            kind: "found",
        });
    });

    it.each([
        [404, { error: "not_playing" }, "missing"],
        [401, { error: "unauthenticated" }, "missing"],
        [503, { error: "game_lookup_failed" }, "failed"],
        [200, { game_id: "g2" }, "failed"],
    ])("answers %i %j as %s", async (status, body, kind) => {
        answer(status, body);

        const recovery = await fetchGameHandoff(new AbortController().signal);

        expect(recovery.kind).toBe(kind);
    });
});
