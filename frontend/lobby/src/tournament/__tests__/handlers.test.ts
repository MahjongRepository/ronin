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

    test("announces a started game with its players in seat order and not their leaving", () => {
        const { handlers, state } = buildTournament();

        handleMessage(handlers, {
            game_id: "g1",
            players: ["Dave", "Carol", "Bob", "Alice"],
            type: "game_started",
        });
        handleMessage(handlers, { count: 0, players: [], type: "presence" });

        expect(chatTexts(state).at(-1)).toBe("A game started: Dave, Carol, Bob, and Alice");
        expect(chatTexts(state).filter((text) => text.endsWith("went offline"))).toEqual([]);
    });

    test("announces a completed game by placement with scores and any other end without a result", () => {
        const { handlers, state } = buildTournament();
        const players = ["Dave", "Carol", "Bob", "Alice"];

        handleMessage(handlers, {
            end_reason: "completed",
            game_id: "g1",
            players,
            result: [
                { final_score: 51, name: "Bob", score: 41_000, seat: 2 },
                { final_score: 8, name: "Dave", score: 28_000, seat: 0 },
                { final_score: -21, name: "Alice", score: 19_000, seat: 3 },
                { final_score: -38, name: "Carol", score: 12_000, seat: 1 },
            ],
            type: "game_ended",
        });
        handleMessage(handlers, {
            end_reason: "abandoned",
            game_id: "g2",
            players,
            result: [{ final_score: null, name: "Dave", score: null, seat: 0 }],
            type: "game_ended",
        });

        expect(chatTexts(state).at(-2)).toBe(
            "A game ended: 1. Bob (41,000), 2. Dave (28,000), 3. Alice (19,000), and 4. Carol (12,000)",
        );
        expect(chatTexts(state).at(-1)).toBe(
            "A game ended without a result: Dave, Carol, Bob, and Alice",
        );
    });

    test("appends a chat message with its sender", () => {
        const { handlers, state } = buildTournament();

        handleMessage(handlers, { player_name: "Bob", text: "good luck", type: "chat" });

        expect(state.chatMessages.at(-1)).toMatchObject({ sender: "Bob", text: "good luck" });
    });

    test("shows the chat history as its chat in place of what it showed", () => {
        const { handlers, state } = buildTournament();
        handleMessage(handlers, { player_name: "Bob", text: "good luck", type: "chat" });
        const { container, render } = mountPage(state);

        handleMessage(handlers, {
            messages: [
                { player_name: "Alice", text: "hello", time: 1_794_393_000 },
                { player_name: "Bob", text: "good luck", time: 1_794_393_060 },
            ],
            type: "chat_history",
        });
        render();

        const entries = [...container.querySelectorAll(".room-chat-entry")].map((entry) => [
            entry.querySelector(".room-chat-sender")?.textContent,
            entry.querySelector(".room-chat-text")?.textContent,
        ]);
        expect(entries).toEqual([
            ["Alice", "hello"],
            ["Bob", "good luck"],
        ]);
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
