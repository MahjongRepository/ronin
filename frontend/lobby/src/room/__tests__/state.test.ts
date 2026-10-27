import { describe, expect, test } from "vitest";

import { createRoomState, describeStartBlocker, getMyReadyState } from "@/room/state";

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

describe("describeStartBlocker", () => {
    test("names every guest who is not ready, ignoring the host and bots, and guesses no other reason", () => {
        const state = createRoomState();
        state.players = [
            { is_bot: false, is_owner: true, name: "host", ready: false },
            { is_bot: false, is_owner: false, name: "dev2", ready: false },
            { is_bot: true, is_owner: false, name: "Bot", ready: true },
            { is_bot: false, is_owner: false, name: "dev3", ready: false },
        ];
        expect(describeStartBlocker(state)).toBe("Waiting for dev2 and dev3 to get ready.");

        state.players = state.players.map((player) => ({ ...player, ready: true }));
        expect(describeStartBlocker(state)).toBeNull();
    });
});
