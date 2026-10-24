import { afterEach, describe, expect, test } from "vitest";

import { storeGameSession } from "@/session";

afterEach(() => {
    sessionStorage.clear();
});

describe("storeGameSession", () => {
    test("writes the handoff entry the game client reads", () => {
        storeGameSession("game-1", "ws://localhost/ws", "ticket-xyz");
        expect(JSON.parse(sessionStorage.getItem("game_session:game-1") ?? "null")).toEqual({
            gameTicket: "ticket-xyz",
            wsUrl: "ws://localhost/ws",
        });
    });
});
