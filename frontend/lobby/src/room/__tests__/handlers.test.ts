import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
    JOIN_RETRY_DELAY_MS,
    MAX_JOIN_RETRIES,
    buildActionCallbacks,
    buildMessageHandlers,
    handleMessage,
} from "@/room/handlers";
import { createRoomState } from "@/room/state";

function buildRoom() {
    const state = createRoomState();
    const rejoin = vi.fn();
    const handlers = buildMessageHandlers(state, vi.fn(), rejoin);
    return { handlers, rejoin, state };
}

function takeSeat(handlers: ReturnType<typeof buildRoom>["handlers"]): void {
    handleMessage(handlers, {
        can_start: false,
        is_owner: false,
        player_name: "Alice",
        players: [],
        type: "room_joined",
    });
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
        vi.advanceTimersByTime(JOIN_RETRY_DELAY_MS);
        expect(rejoin).toHaveBeenCalledTimes(1);

        handleMessage(handlers, { message: "room_transitioning", type: "error" });
        vi.advanceTimersByTime(JOIN_RETRY_DELAY_MS);
        expect(rejoin).toHaveBeenCalledTimes(2);
        expect(state.chatMessages.map((entry) => entry.text)).toEqual(["The game is starting."]);
    });

    test("does not rejoin when a seated player is refused during the start", () => {
        const { handlers, rejoin, state } = buildRoom();
        takeSeat(handlers);

        handleMessage(handlers, { message: "room_transitioning", type: "error" });
        vi.advanceTimersByTime(JOIN_RETRY_DELAY_MS);

        expect(rejoin).not.toHaveBeenCalled();
        expect(state.chatMessages.map((entry) => entry.text)).toEqual([
            "You joined the table",
            "The game is starting.",
        ]);
    });

    test.each([
        ["already_in_queue", "You are searching for a match. Cancel the search first."],
        ["room_full", "This table filled up before you joined."],
    ])("ends the page on a %s refusal with its reason instead of a chat line", (code, text) => {
        const { handlers, rejoin, state } = buildRoom();

        handleMessage(handlers, { message: code, type: "error" });

        expect(state.pageError).toEqual({ code, seatedRoomId: undefined, text });
        expect(state.chatMessages).toEqual([]);
        expect(rejoin).not.toHaveBeenCalled();
    });

    test("ends the page when another tab takes over the seat", () => {
        const { handlers, state } = buildRoom();
        takeSeat(handlers);

        handleMessage(handlers, { message: "replaced_by_new_connection", type: "error" });

        expect(state.pageError?.code).toBe("replaced_by_new_connection");
    });

    test("ends the page once the join retries run out", () => {
        const { handlers, rejoin, state } = buildRoom();

        for (let attempt = 0; attempt <= MAX_JOIN_RETRIES; attempt += 1) {
            handleMessage(handlers, { message: "room_transitioning", type: "error" });
            vi.advanceTimersByTime(JOIN_RETRY_DELAY_MS);
        }

        expect(rejoin).toHaveBeenCalledTimes(MAX_JOIN_RETRIES);
        expect(state.pageError?.text).toBe(
            "The game did not start in time. Reload the page to try again.",
        );
    });

    test("does not reconnect through a retry scheduled before the page ended", () => {
        const { handlers, rejoin, state } = buildRoom();

        handleMessage(handlers, { message: "room_transitioning", type: "error" });
        handleMessage(handlers, { message: "room_not_found", type: "error" });
        vi.advanceTimersByTime(JOIN_RETRY_DELAY_MS);

        expect(rejoin).not.toHaveBeenCalled();
        expect(state.pageError?.code).toBe("room_not_found");
    });
});

describe("buildActionCallbacks", () => {
    afterEach(() => {
        vi.restoreAllMocks();
    });

    test("leaves for the lobby without a history entry, so Back cannot take the seat again", () => {
        const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});

        buildActionCallbacks(createRoomState()).handleLeaveRoom();

        expect(replace).toHaveBeenCalledWith("/");
    });
});
