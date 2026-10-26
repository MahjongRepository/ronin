import { afterEach, describe, expect, it, vi } from "vitest";

import { RECOVERY, readGameSession, recoverGameSession } from "../game-session.js";

describe("readGameSession", () => {
    afterEach(() => sessionStorage.clear());

    it("reads the socket URL and ticket the lobby stored for the game", () => {
        sessionStorage.setItem(
            "game_session:g-1",
            JSON.stringify({ wsUrl: "ws://game/ws/g-1", gameTicket: "ticket" }),
        );

        expect(readGameSession("g-1")).toEqual({ wsUrl: "ws://game/ws/g-1", gameTicket: "ticket" });
        expect(readGameSession("g-2")).toBeNull();
    });

    it("treats an unparsable or incomplete handoff as missing", () => {
        sessionStorage.setItem("game_session:broken", "{");
        sessionStorage.setItem("game_session:no-ticket", JSON.stringify({ wsUrl: "ws://game" }));

        expect(readGameSession("broken")).toBeNull();
        expect(readGameSession("no-ticket")).toBeNull();
    });
});

describe("recoverGameSession", () => {
    afterEach(() => {
        sessionStorage.clear();
        vi.unstubAllGlobals();
    });

    it("asks the lobby uncached and stores the recovered handoff under its game", async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            Response.json({
                game_id: "g 1",
                ws_url: "wss://game/ws/g 1",
                game_ticket: "ticket",
                game_client_url: "/play",
            }),
        );
        vi.stubGlobal("fetch", fetchMock);

        const recovery = await recoverGameSession();

        expect(fetchMock).toHaveBeenCalledWith(
            "/api/game-session",
            expect.objectContaining({ cache: "no-store", credentials: "same-origin" }),
        );
        expect(recovery).toEqual({
            status: RECOVERY.FOUND,
            gameId: "g 1",
            gameUrl: "/play/g%201",
            session: { wsUrl: "wss://game/ws/g 1", gameTicket: "ticket" },
        });
        expect(readGameSession("g 1")).toEqual({
            wsUrl: "wss://game/ws/g 1",
            gameTicket: "ticket",
        });
    });

    it("tells a player with no game apart from a lookup that failed", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 404 })));
        expect(await recoverGameSession()).toEqual({ status: RECOVERY.MISSING });

        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 503 })));
        expect(await recoverGameSession()).toEqual({ status: RECOVERY.FAILED });

        vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));
        expect(await recoverGameSession()).toEqual({ status: RECOVERY.FAILED });
    });
});
