import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { t } from "@/i18n";
import { OCCUPANCY } from "@/occupancy-errors";
import {
    JOIN_RETRY_DELAY_MS,
    MAX_JOIN_RETRIES,
    MAX_RECONNECT_ATTEMPTS,
    ROOM_ERROR_CODES,
    buildActionCallbacks,
    buildMessageHandlers,
    buildStatusHandler,
    describeRoomError,
    handleMessage,
    reconnectOnResume,
} from "@/room/handlers";
import { canAct, createRoomState, isConnectionLost } from "@/room/state";

function buildRoom() {
    const state = createRoomState();
    const rejoin = vi.fn();
    const handlers = buildMessageHandlers(state, vi.fn(), rejoin);
    const onStatus = buildStatusHandler(state, vi.fn(), rejoin);
    function loseConnection(): void {
        onStatus("disconnected");
    }
    return { handlers, loseConnection, rejoin, state };
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
        ["already_in_queue", "You're already searching for a match. Cancel that search first."],
        ["room_full", "This table filled up before you joined."],
    ])("ends the page on a %s refusal with its reason instead of a chat line", (code, text) => {
        const { handlers, rejoin, state } = buildRoom();

        handleMessage(handlers, { message: code, type: "error" });

        expect(state.pageError).toEqual({ code, seatedRoomId: undefined });
        expect(describeRoomError(state.pageError?.code)).toBe(text);
        expect(state.chatMessages).toEqual([]);
        expect(rejoin).not.toHaveBeenCalled();
    });

    test("ends the page when another tab takes over the seat", () => {
        const { handlers, state } = buildRoom();
        takeSeat(handlers);

        handleMessage(handlers, { message: "replaced_by_new_connection", type: "error" });

        expect(state.pageError?.code).toBe("replaced_by_new_connection");
    });

    test("ends the page with the expiry notice, not a reconnect, when the server closes an expired table", () => {
        const { handlers, loseConnection, rejoin, state } = buildRoom();
        takeSeat(handlers);

        handleMessage(handlers, { message: "room_expired", type: "error" });
        loseConnection();
        vi.runAllTimers();

        expect(describeRoomError(state.pageError?.code)).toBe(t("room.error.room_expired"));
        expect(rejoin).not.toHaveBeenCalled();
    });

    test("ends the page once the join retries run out", () => {
        const { handlers, rejoin, state } = buildRoom();

        for (let attempt = 0; attempt <= MAX_JOIN_RETRIES; attempt += 1) {
            handleMessage(handlers, { message: "room_transitioning", type: "error" });
            vi.advanceTimersByTime(JOIN_RETRY_DELAY_MS);
        }

        expect(rejoin).toHaveBeenCalledTimes(MAX_JOIN_RETRIES);
        expect(describeRoomError(state.pageError?.code)).toBe(
            "The game didn't start in time. Reload the page to try again.",
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

describe("buildStatusHandler", () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    test("reconnects a lost seat after a delay that doubles", () => {
        const { handlers, loseConnection, rejoin, state } = buildRoom();
        takeSeat(handlers);

        loseConnection();
        expect(state.connectionStatus).toBe("connecting");
        vi.advanceTimersByTime(1000);

        loseConnection();
        vi.advanceTimersByTime(1999);
        expect(rejoin).toHaveBeenCalledTimes(1);
        vi.advanceTimersByTime(1);
        expect(rejoin).toHaveBeenCalledTimes(2);
    });

    test("takes the seat back without a join line and starts the delays over", () => {
        const { handlers, loseConnection, state } = buildRoom();
        takeSeat(handlers);

        loseConnection();
        vi.runOnlyPendingTimers();
        state.connectionStatus = "connected";
        expect(canAct(state)).toBe(false);
        takeSeat(handlers);

        expect(canAct(state)).toBe(true);
        expect(state.reconnectAttempts).toBe(0);
        expect(state.chatMessages.map((entry) => entry.text)).toEqual(["You joined the table"]);
    });

    test("ends the page when the reconnect finds the seat gone", () => {
        const { handlers, loseConnection, state } = buildRoom();
        takeSeat(handlers);

        loseConnection();
        vi.runOnlyPendingTimers();
        handleMessage(handlers, { message: "room_not_found", type: "error" });

        expect(state.pageError?.code).toBe("room_not_found");
    });

    test("shows the lost connection once the reconnects run out", () => {
        const { handlers, loseConnection, rejoin, state } = buildRoom();
        takeSeat(handlers);

        for (let attempt = 0; attempt <= MAX_RECONNECT_ATTEMPTS; attempt += 1) {
            loseConnection();
            vi.runOnlyPendingTimers();
        }

        expect(rejoin).toHaveBeenCalledTimes(MAX_RECONNECT_ATTEMPTS);
        expect(isConnectionLost(state)).toBe(true);
    });

    test("reconnects a seated page at once on resume, dropping the pending delay", () => {
        const { handlers, loseConnection, rejoin, state } = buildRoom();
        reconnectOnResume(state, rejoin);
        expect(rejoin).not.toHaveBeenCalled();
        takeSeat(handlers);

        loseConnection();
        reconnectOnResume(state, rejoin);
        vi.runOnlyPendingTimers();

        expect(rejoin).toHaveBeenCalledTimes(1);
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

describe("describeRoomError", () => {
    afterEach(() => {
        document.documentElement.lang = "";
        vi.restoreAllMocks();
    });

    test.each(["en", "ja", "ru"])(
        "words every room error and occupancy code it handles in %s without the generic fallback",
        (locale) => {
            document.documentElement.lang = locale;
            const report = vi.spyOn(console, "error").mockImplementation(() => undefined);

            const texts = [...ROOM_ERROR_CODES, ...Object.values(OCCUPANCY)].map(describeRoomError);

            expect(texts).not.toContain(t("room.error.unknown"));
            expect(new Set(texts).size).toBe(texts.length);
            expect(report).not.toHaveBeenCalled();
        },
    );

    test("shows the generic failure for an unknown code and reports the code, never the code itself", () => {
        const report = vi.spyOn(console, "error").mockImplementation(() => undefined);

        const text = describeRoomError("server_exploded");

        expect(text).toBe("Something went wrong at this table.");
        expect(report).toHaveBeenCalledWith(
            "i18n error",
            expect.objectContaining({ key: "room.error.server_exploded" }),
        );
    });
});
