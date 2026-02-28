import {
    clearGameSession,
    clearSessionData,
    getGameSession,
    getGameTicket,
    setGameTicket,
    storeGameSession,
} from "@/session-storage";
import { afterEach, describe, expect, test } from "vitest";

afterEach(() => {
    sessionStorage.clear();
});

describe("game ticket", () => {
    test("round-trip: set then get", () => {
        setGameTicket("abc-123");
        expect(getGameTicket()).toBe("abc-123");
    });

    test("returns null when not set", () => {
        expect(getGameTicket()).toBeNull();
    });
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

describe("clearSessionData", () => {
    test("clears legacy session keys", () => {
        sessionStorage.setItem("ws_url", "ws://x");
        sessionStorage.setItem("game_ticket", "t");
        sessionStorage.setItem("room_id", "r");
        clearSessionData();
        expect(sessionStorage.getItem("ws_url")).toBeNull();
        expect(sessionStorage.getItem("game_ticket")).toBeNull();
        expect(sessionStorage.getItem("room_id")).toBeNull();
    });

    test("clears game session when gameId provided", () => {
        storeGameSession("game-1", "ws://x", "t");
        clearSessionData("game-1");
        expect(getGameSession("game-1")).toBeNull();
    });

    test("does not clear game session when gameId omitted", () => {
        storeGameSession("game-1", "ws://x", "t");
        clearSessionData();
        expect(getGameSession("game-1")).not.toBeNull();
    });
});
