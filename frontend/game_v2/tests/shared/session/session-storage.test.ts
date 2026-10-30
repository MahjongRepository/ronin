import { afterEach, describe, expect, test } from "vitest";

import { clearGameSession, getGameSession, storeGameSession } from "@/shared/session";

afterEach(() => {
    sessionStorage.clear();
});

describe("game session", () => {
    test("round-trip: store then retrieve", () => {
        storeGameSession("game-1", "ws://localhost/ws", "ticket-xyz");
        const session = getGameSession("game-1");
        expect(session).toEqual({ gameTicket: "ticket-xyz", wsUrl: "ws://localhost/ws" });
    });

    test("returns null for unknown game ID", () => {
        expect(getGameSession("nonexistent")).toBeNull();
    });

    test("returns null when stored JSON is malformed", () => {
        sessionStorage.setItem("game_session:bad", "not-json{{{");
        expect(getGameSession("bad")).toBeNull();
    });

    test("returns null when stored JSON is missing required fields", () => {
        sessionStorage.setItem("game_session:partial", JSON.stringify({ wsUrl: "ws://x" }));
        expect(getGameSession("partial")).toBeNull();
    });

    test("returns null when fields have wrong types", () => {
        sessionStorage.setItem(
            "game_session:wrong",
            JSON.stringify({ gameTicket: true, wsUrl: 123 }),
        );
        expect(getGameSession("wrong")).toBeNull();
    });

    test("clearGameSession removes only the targeted game", () => {
        storeGameSession("game-a", "ws://a", "ticket-a");
        storeGameSession("game-b", "ws://b", "ticket-b");
        clearGameSession("game-a");
        expect(getGameSession("game-a")).toBeNull();
        expect(getGameSession("game-b")).not.toBeNull();
    });
});
