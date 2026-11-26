import { afterEach, describe, expect, it, vi } from "vitest";

import { returnToGame } from "@/lobby/handlers";
import { type LobbyState, createLobbyState } from "@/lobby/state";

const LIVE_GAME = {
    game_client_url: "/play",
    game_id: "game-1",
    game_ticket: "ticket-1",
    ws_url: "ws://game/ws",
};

const context = { isDisposed: () => false, navigate: () => {}, render: () => {} };

function answerGameSession(status: number, body: unknown): void {
    vi.stubGlobal(
        "fetch",
        vi.fn(async () => Response.json(body, { status })),
    );
}

function playingState(): LobbyState {
    const state = createLobbyState(null);
    state.playing = true;
    return state;
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

        await returnToGame(playingState(), context);

        expect(JSON.parse(sessionStorage.getItem("game_session:game-1") ?? "null")).toEqual({
            gameTicket: "ticket-1",
            wsUrl: "ws://game/ws",
        });
        expect(replace).toHaveBeenCalledExactlyOnceWith("/play/game-1");
    });

    it.each([
        {
            body: { error: "not_playing" },
            expected: { playing: false, returnFailed: false },
            status: 404,
            when: "the game ended meanwhile",
        },
        {
            body: { error: "game_lookup_failed" },
            expected: { playing: true, returnFailed: true },
            status: 503,
            when: "the game server could not be asked",
        },
    ])("stays in the lobby when $when", async ({ body, expected, status }) => {
        const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
        answerGameSession(status, body);
        const state = playingState();

        await returnToGame(state, context);

        expect(replace).not.toHaveBeenCalled();
        expect({ ...expected, returning: false }).toEqual({
            playing: state.playing,
            returnFailed: state.returnFailed,
            returning: state.returning,
        });
    });
});
