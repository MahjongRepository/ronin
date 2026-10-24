import { afterEach, describe, expect, it } from "vitest";

import { readGameSession } from "../game-session.js";

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
