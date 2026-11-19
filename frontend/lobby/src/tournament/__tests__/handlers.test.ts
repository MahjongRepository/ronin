import { afterEach, describe, expect, test, vi } from "vitest";

import { t } from "@/i18n";
import {
    TOURNAMENT_ERROR_CODES,
    buildMessageHandlers,
    buildStatusHandler,
    describeTournamentError,
    handleMessage,
} from "@/tournament/handlers";
import {
    createTournamentState,
    isConnectionLost,
    readTournamentConfigAnswer,
} from "@/tournament/state";
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
            renderTournament({
                actions: {
                    deleteTournament: () => {},
                    renameTournament: () => {},
                    sendChat: () => false,
                },
                config: null,
                container,
                state,
                tournamentId: "cup",
            }),
    };
}

function chatTexts(state: ReturnType<typeof createTournamentState>): string[] {
    return state.chatMessages.map((entry) => entry.text);
}

describe("buildMessageHandlers", () => {
    test("announces who came online and who left only from the server's presence events", () => {
        const { handlers, state } = buildTournament();

        handleMessage(handlers, { player_name: "Carol", time: 1, type: "player_online" });
        handleMessage(handlers, { player_name: "Bob", time: 2, type: "player_offline" });
        handleMessage(handlers, { count: 2, players: ["Alice", "Carol"], type: "presence" });
        handleMessage(handlers, {
            count: 3,
            players: ["Alice", "Carol", "Dave"],
            type: "presence",
        });

        expect(state.players).toEqual(["Alice", "Carol", "Dave"]);
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

    test("announces a completed game's players with scores in placement order and any other end without a result", () => {
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
            "A game ended: Bob (41,000), Dave (28,000), Alice (19,000), and Carol (12,000)",
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

    test("shows the server history as its chat in place of what it showed", () => {
        const { handlers, state } = buildTournament();
        handleMessage(handlers, { player_name: "Bob", text: "good luck", type: "chat" });
        const { container, render } = mountPage(state);

        handleMessage(handlers, {
            messages: [
                { player_name: "Carol", time: 1_794_393_000, type: "player_online" },
                { player_name: "Bob", text: "good luck", time: 1_794_393_060, type: "chat" },
                {
                    end_reason: "abandoned",
                    game_id: "g1",
                    players: ["Dave", "Carol", "Bob", "Alice"],
                    result: [],
                    time: 1_794_395_400,
                    type: "game_ended",
                },
                { player_name: "Carol", time: 1_794_395_460, type: "player_offline" },
            ],
            type: "history",
        });
        render();

        const entries = [...container.querySelectorAll(".room-chat-entry")].map((entry) => [
            entry.querySelector(".room-chat-sender")?.textContent,
            entry.querySelector(".room-chat-text")?.textContent,
        ]);
        expect(entries).toEqual([
            [undefined, "Carol is online"],
            ["Bob", "good luck"],
            [undefined, "A game ended without a result: Dave, Carol, Bob, and Alice"],
            [undefined, "Carol went offline"],
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

describe("renderTournament", () => {
    const config = {
        chatMaxLength: 100,
        isOwner: true,
        name: "Cup",
        nameMaxLength: 80,
        shareUrl: "https://ronin.test/tournaments/cup",
        wsUrl: "wss://ronin.test/ws/tournaments/cup",
    };

    function renderWith(isOwner: boolean): HTMLElement {
        const state = createTournamentState();
        state.name = "Cup";
        const container = document.createElement("div");
        renderTournament({
            actions: {
                deleteTournament: () => {},
                renameTournament: () => {},
                sendChat: () => false,
            },
            config: { ...config, isOwner },
            container,
            state,
            tournamentId: "cup",
        });
        return container;
    }

    test("shows the API hints, rename and delete to the owner only", () => {
        const owner = renderWith(true);
        const player = renderWith(false);

        expect(owner.querySelector(".tournament-owner-api")?.textContent).toContain(
            "POST /api/tournaments/cup/games",
        );
        expect(owner.querySelector(".tournament-delete")).not.toBeNull();
        expect(player.querySelector(".tournament-owner-api")).toBeNull();
        expect(player.querySelector<HTMLInputElement>("#tournament-share-link")?.value).toBe(
            config.shareUrl,
        );
    });
});

describe("readTournamentConfigAnswer", () => {
    test("tells a deleted tournament from a page that failed to load", () => {
        const gone = readTournamentConfigAnswer({
            data: {},
            error: "tournament_not_found",
            ok: false,
        });
        const failed = readTournamentConfigAnswer({ data: { name: "Cup" }, ok: true });

        expect([gone.kind, failed.kind]).toEqual(["gone", "failed"]);
    });
});
