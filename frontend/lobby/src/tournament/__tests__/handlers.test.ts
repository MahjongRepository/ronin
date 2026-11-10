import { afterEach, describe, expect, test, vi } from "vitest";

import { t } from "@/i18n";
import {
    TOURNAMENT_ERROR_CODES,
    buildMessageHandlers,
    buildStatusHandler,
    describeTournamentError,
    handleMessage,
} from "@/tournament/handlers";
import { createTournamentState, isConnectionLost } from "@/tournament/state";
import { renderTournament } from "@/tournament/ui";

function buildTournament() {
    const state = createTournamentState();
    const handlers = buildMessageHandlers(state, vi.fn());
    handleMessage(handlers, { players: ["Alice", "Bob"], type: "joined" });
    return { handlers, state };
}

function mountPage(state: ReturnType<typeof createTournamentState>) {
    const container = document.createElement("div");
    return {
        container,
        render: () =>
            renderTournament({ chatMaxLength: 100, container, sendChat: () => false, state }),
    };
}

function chatTexts(state: ReturnType<typeof createTournamentState>): string[] {
    return state.chatMessages.map((entry) => entry.text);
}

describe("buildMessageHandlers", () => {
    test("announces who came online and who left by diffing the online list", () => {
        const { handlers, state } = buildTournament();

        handleMessage(handlers, { count: 2, players: ["Alice", "Carol"], type: "presence" });

        expect(state.players).toEqual(["Alice", "Carol"]);
        expect(chatTexts(state)).toEqual([
            "You're online in this tournament",
            "Carol is online",
            "Bob went offline",
        ]);
    });

    test("appends a chat message with its sender", () => {
        const { handlers, state } = buildTournament();

        handleMessage(handlers, { player_name: "Bob", text: "good luck", type: "chat" });

        expect(state.chatMessages.at(-1)).toMatchObject({ sender: "Bob", text: "good luck" });
    });

    test("ends the page when another tab takes over the connection", () => {
        const { handlers, state } = buildTournament();

        handleMessage(handlers, { message: "replaced_by_new_connection", type: "error" });

        expect(state.pageError).toBe("replaced_by_new_connection");
        expect(isConnectionLost(state)).toBe(false);
    });
});

describe("buildStatusHandler", () => {
    afterEach(() => {
        vi.useRealTimers();
    });

    test("hides the online list behind a connecting notice while a lost socket waits to reconnect", () => {
        vi.useFakeTimers();
        const { state } = buildTournament();
        const rejoin = vi.fn();
        const { container, render } = mountPage(state);

        buildStatusHandler(state, render, rejoin)("disconnected");

        expect(state.reconnectTimer).not.toBeNull();
        expect(rejoin).not.toHaveBeenCalled();
        expect(container.querySelectorAll(".room-player-item")).toHaveLength(0);
        expect(container.querySelector("#tournament-online-title")?.textContent?.trim()).toBe(
            "Online",
        );
        expect(container.querySelector("[role=status]")?.textContent).toBe("Connecting…");
    });
});

describe("describeTournamentError", () => {
    afterEach(() => {
        document.documentElement.lang = "";
        vi.restoreAllMocks();
    });

    test.each(["en", "ja", "ru"])(
        "words every tournament error code it handles in %s without the generic fallback",
        (locale) => {
            document.documentElement.lang = locale;
            const report = vi.spyOn(console, "error").mockImplementation(() => undefined);

            const texts = TOURNAMENT_ERROR_CODES.map(describeTournamentError);

            expect(texts).not.toContain(t("tournament.error.unknown"));
            expect(new Set(texts).size).toBe(texts.length);
            expect(report).not.toHaveBeenCalled();
        },
    );
});
