import { afterEach, describe, expect, it, vi } from "vitest";

import { type LiveGameReturn, createLiveGameReturn, returnToGame } from "@/session";

const LIVE_GAME = {
    game_client_url: "/play",
    game_id: "game-1",
    game_ticket: "ticket-1",
    seat_version: 2,
    ws_url: "ws://game/ws",
};

const context = { isDisposed: () => false, render: () => {} };

function answerGameSession(status: number, body: unknown): void {
    vi.stubGlobal(
        "fetch",
        vi.fn(async () => Response.json(body, { status })),
    );
}

function playing(): LiveGameReturn {
    return { ...createLiveGameReturn(), playing: true };
}

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    sessionStorage.clear();
});

describe("returnToGame", () => {
    it("enters the user's game with the session it fetched at the click", async () => {
        const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
        answerGameSession(200, LIVE_GAME);

        await returnToGame(playing(), context);

        expect(JSON.parse(sessionStorage.getItem("game_session:game-1") ?? "null")).toEqual({
            claimId: expect.any(String),
            gameTicket: "ticket-1",
            seatVersion: 2,
            wsUrl: "ws://game/ws",
        });
        expect(replace).toHaveBeenCalledExactlyOnceWith("/play/game-1");
    });

    it.each([
        {
            body: { error: "not_playing" },
            expected: { playing: false, returnFailed: false, returning: false },
            status: 404,
            when: "the game ended meanwhile",
        },
        {
            body: { error: "game_lookup_failed" },
            expected: { playing: true, returnFailed: true, returning: false },
            status: 503,
            when: "the game server could not be asked",
        },
    ])("stays on the page when $when", async ({ body, expected, status }) => {
        const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
        answerGameSession(status, body);
        const live = playing();

        await returnToGame(live, context);

        expect(replace).not.toHaveBeenCalled();
        expect(live).toEqual(expected);
    });
});
