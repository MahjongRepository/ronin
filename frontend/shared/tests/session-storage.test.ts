import {
    claimGameSession,
    clearAllGameSessions,
    clearGameSession,
    getGameSession,
    storeGameSession,
} from "@ronin/shared/session-storage";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => {
    sessionStorage.clear();
});

describe("game session", () => {
    it("round-trip: store then retrieve", () => {
        storeGameSession("game-1", claimGameSession("ws://localhost/ws", "ticket-xyz", 2));
        const session = getGameSession("game-1");
        expect(session).toEqual({
            claimId: expect.stringMatching(/^[0-9a-f]{32}$/u),
            gameTicket: "ticket-xyz",
            seatVersion: 2,
            wsUrl: "ws://localhost/ws",
        });
        expect(JSON.parse(sessionStorage.getItem("game_session:game-1") ?? "null")).toEqual(
            session,
        );
    });

    it("makes a new claim for every handoff of the same seat", () => {
        const first = claimGameSession("ws://a", "ticket-a", 0);
        const second = claimGameSession("ws://a", "ticket-a", 0);
        expect(first.claimId).not.toBe(second.claimId);
    });

    it("returns null for unknown game ID", () => {
        expect(getGameSession("nonexistent")).toBeNull();
    });

    it("returns null when stored JSON is malformed", () => {
        sessionStorage.setItem("game_session:bad", "not-json{{{");
        expect(getGameSession("bad")).toBeNull();
    });

    it("returns null when stored JSON is missing required fields", () => {
        sessionStorage.setItem("game_session:partial", JSON.stringify({ wsUrl: "ws://x" }));
        expect(getGameSession("partial")).toBeNull();
    });

    it("returns null when fields have wrong types", () => {
        sessionStorage.setItem(
            "game_session:wrong",
            JSON.stringify({ claimId: "c", gameTicket: "t", seatVersion: -1, wsUrl: "ws://x" }),
        );
        expect(getGameSession("wrong")).toBeNull();
    });

    it("clearGameSession removes only the targeted game", () => {
        storeGameSession("game-a", claimGameSession("ws://a", "ticket-a", 0));
        storeGameSession("game-b", claimGameSession("ws://b", "ticket-b", 0));
        clearGameSession("game-a");
        expect(getGameSession("game-a")).toBeNull();
        expect(getGameSession("game-b")).not.toBeNull();
    });

    it("clearAllGameSessions removes every game's handoff and keeps the tab's other keys", () => {
        storeGameSession("game-a", claimGameSession("ws://a", "ticket-a", 0));
        storeGameSession("game-b", claimGameSession("ws://b", "ticket-b", 0));
        sessionStorage.setItem("other", "kept");
        clearAllGameSessions();
        expect(getGameSession("game-a")).toBeNull();
        expect(getGameSession("game-b")).toBeNull();
        expect(sessionStorage.getItem("other")).toBe("kept");
    });
});
