import { createRoomState, getMyReadyState } from "@/lobby/room/state";
import { describe, expect, test } from "vitest";

describe("getMyReadyState", () => {
    test("returns true when the player is ready", () => {
        const state = createRoomState();
        state.currentPlayerName = "Alice";
        state.players = [{ is_bot: false, is_owner: false, name: "Alice", ready: true }];
        expect(getMyReadyState(state)).toBe(true);
    });

    test("returns false when the player is not ready", () => {
        const state = createRoomState();
        state.currentPlayerName = "Alice";
        state.players = [{ is_bot: false, is_owner: false, name: "Alice", ready: false }];
        expect(getMyReadyState(state)).toBe(false);
    });

    test("returns false when player is not in the list", () => {
        const state = createRoomState();
        state.currentPlayerName = "Alice";
        state.players = [{ is_bot: false, is_owner: false, name: "Bob", ready: true }];
        expect(getMyReadyState(state)).toBe(false);
    });

    test("ignores bot with the same name as the player", () => {
        const state = createRoomState();
        state.currentPlayerName = "Alice";
        state.players = [{ is_bot: true, is_owner: false, name: "Alice", ready: true }];
        expect(getMyReadyState(state)).toBe(false);
    });

    test("finds the human player among bots with same name", () => {
        const state = createRoomState();
        state.currentPlayerName = "Alice";
        state.players = [
            { is_bot: true, is_owner: false, name: "Alice", ready: true },
            { is_bot: false, is_owner: false, name: "Alice", ready: false },
        ];
        expect(getMyReadyState(state)).toBe(false);
    });

    test("returns false when player list is empty", () => {
        const state = createRoomState();
        state.currentPlayerName = "Alice";
        expect(getMyReadyState(state)).toBe(false);
    });
});
