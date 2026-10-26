import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { buildMessageHandlers, handleMessage } from "@/room/handlers";
import { createRoomState } from "@/room/state";

function buildRoom() {
    const state = createRoomState();
    const rejoin = vi.fn();
    const updateUI = {
        updateActionButton: vi.fn(),
        updateChatPanel: vi.fn(),
        updatePlayerList: vi.fn(),
        updateStatusDisplay: vi.fn(),
    };
    const handlers = buildMessageHandlers(state, updateUI, rejoin);
    return { handlers, rejoin, state };
}

describe("buildMessageHandlers", () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    test("rejoins after a delay while the game starts, announcing it once", () => {
        const { handlers, rejoin, state } = buildRoom();

        handleMessage(handlers, { message: "room_transitioning", type: "error" });
        expect(rejoin).not.toHaveBeenCalled();
        vi.advanceTimersByTime(2000);
        expect(rejoin).toHaveBeenCalledTimes(1);

        handleMessage(handlers, { message: "room_transitioning", type: "error" });
        vi.advanceTimersByTime(2000);
        expect(rejoin).toHaveBeenCalledTimes(2);
        expect(state.chatMessages.map((entry) => entry.text)).toEqual(["The game is starting."]);
    });

    test("does not rejoin when a seated player is refused during the start", () => {
        const { handlers, rejoin, state } = buildRoom();
        handleMessage(handlers, {
            can_start: false,
            is_owner: false,
            player_name: "Alice",
            players: [],
            type: "room_joined",
        });

        handleMessage(handlers, { message: "room_transitioning", type: "error" });
        vi.advanceTimersByTime(2000);

        expect(rejoin).not.toHaveBeenCalled();
        expect(state.chatMessages.map((entry) => entry.text)).toEqual([
            "Joined room",
            "The game is starting.",
        ]);
    });
});
