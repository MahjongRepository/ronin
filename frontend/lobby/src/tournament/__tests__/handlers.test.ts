import { afterEach, describe, expect, test, vi } from "vitest";

import { t } from "@/i18n";
import {
    TOURNAMENT_ERROR_CODES,
    buildMessageHandlers,
    buildStatusHandler,
    describeTournamentError,
    handleMessage,
} from "@/tournament/handlers";
import { type PlayedGame } from "@/tournament/played-games";
import {
    type TournamentState,
    type TournamentTab,
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
                    selectTab: () => {},
                    sendChat: () => false,
                    setChatOpen: () => {},
                    showAllPlayed: () => {},
                },
                config: null,
                container,
                state,
                tournamentId: "cup",
            }),
    };
}

const PLAYERS = ["Dave", "Carol", "Bob", "Alice"];

function completedGame(gameId: string): PlayedGame {
    return {
        endReason: "completed",
        endedAt: new Date(),
        gameId,
        players: PLAYERS,
        ranked: PLAYERS.map((name, index) => ({ finalScore: 5.1 - index * 3, name })),
    };
}

function squeezedText(element: Element | null | undefined): string | undefined {
    return element?.textContent?.replace(/\s+/g, " ").trim();
}

describe("buildMessageHandlers", () => {
    test("keeps who is online from presence and announces no presence or game in the chat", () => {
        const { handlers, state } = buildTournament();

        handleMessage(handlers, { count: 2, players: ["Alice", "Carol"], type: "presence" });
        handleMessage(handlers, {
            game_id: "g1",
            players: ["Dave", "Carol", "Bob", "Alice"],
            type: "game_started",
        });

        expect(state.players).toEqual([]);
        expect(state.chatMessages).toEqual([]);
    });

    test("keeps the ended games from the join and adds an ended game once, latest end first, with completed results in points", () => {
        const state = createTournamentState();
        const handlers = buildMessageHandlers(state, vi.fn());
        const players = ["Dave", "Carol", "Bob", "Alice"];
        handleMessage(handlers, {
            played: [
                {
                    end_reason: "abandoned",
                    ended_at: 1_700_000_200,
                    game_id: "g1",
                    players,
                    result: [],
                },
            ],
            players: [],
            type: "joined",
        });
        const ended = {
            end_reason: "completed",
            ended_at: 1_700_000_100,
            game_id: "g2",
            players,
            result: [
                { final_score: 51, name: "Bob", score: 41_000, seat: 2 },
                { final_score: 8, name: "Dave", score: 28_000, seat: 0 },
                { final_score: -21, name: "Alice", score: 19_000, seat: 3 },
                { final_score: -38, name: "Carol", score: 12_000, seat: 1 },
            ],
            type: "game_ended",
        };

        handleMessage(handlers, ended);
        handleMessage(handlers, ended);

        expect(state.played.map((game) => [game.gameId, game.ranked])).toEqual([
            ["g1", null],
            [
                "g2",
                [
                    { finalScore: 5.1, name: "Bob" },
                    { finalScore: 0.8, name: "Dave" },
                    { finalScore: -2.1, name: "Alice" },
                    { finalScore: -3.8, name: "Carol" },
                ],
            ],
        ]);
    });

    test("keeps the current games from the join, adds started ones and drops ended ones", () => {
        const state = createTournamentState();
        const handlers = buildMessageHandlers(state, vi.fn());
        handleMessage(handlers, {
            games: [{ game_id: "g1", players: ["A", "B", "C", "D"], started_at: 1_700_000_000 }],
            players: [],
            type: "joined",
        });

        handleMessage(handlers, {
            game_id: "g2",
            players: ["E", "F", "G", "H"],
            type: "game_started",
        });
        handleMessage(handlers, {
            end_reason: "abandoned",
            game_id: "g1",
            players: ["A"],
            type: "game_ended",
        });

        expect(state.games.map((game) => [game.gameId, game.players])).toEqual([
            ["g2", ["E", "F", "G", "H"]],
        ]);
    });

    test("appends a chat message with its sender and counts it unread only while the chat is folded", () => {
        const { handlers, state } = buildTournament();

        handleMessage(handlers, { player_name: "Bob", text: "good luck", type: "chat" });
        state.chatOpen = true;
        handleMessage(handlers, { player_name: "Carol", text: "thanks", type: "chat" });

        expect(state.chatMessages.at(-1)).toMatchObject({ sender: "Carol", text: "thanks" });
        expect(state.chatUnread).toBe(1);
    });

    test("shows the server history as its chat in place of what it showed", () => {
        const { handlers, state } = buildTournament();
        handleMessage(handlers, { player_name: "Bob", text: "good luck", type: "chat" });
        const { container, render } = mountPage(state);

        handleMessage(handlers, {
            messages: [
                { player_name: "Bob", text: "good luck", time: 1_794_393_060, type: "chat" },
                { player_name: "Carol", text: "thanks", time: 1_794_395_460, type: "chat" },
            ],
            type: "history",
        });
        render();

        const entries = [...container.querySelectorAll(".room-chat-entry")].map((entry) => [
            entry.querySelector(".room-chat-sender")?.textContent,
            entry.querySelector(".room-chat-text")?.textContent,
        ]);
        expect(entries).toEqual([
            ["Bob", "good luck"],
            ["Carol", "thanks"],
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

    test("hides who is online behind a connecting notice while a lost socket waits to reconnect", () => {
        vi.useFakeTimers();
        const { state } = buildTournament();
        const rejoin = vi.fn();
        const { container, render } = mountPage(state);

        buildStatusHandler(state, render, rejoin)("disconnected");

        expect(state.reconnectTimer).not.toBeNull();
        expect(rejoin).not.toHaveBeenCalled();
        expect(container.querySelector(".tournament-online")).toBeNull();
        expect(container.querySelector(".tournament-played")).not.toBeNull();
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
        wsUrl: "wss://ronin.test/ws/tournaments/cup",
    };

    function renderWith(
        isOwner: boolean,
        tab: TournamentTab,
        setUp: (state: TournamentState) => void = () => {},
    ): HTMLElement {
        const state = createTournamentState();
        state.name = "Cup";
        state.tab = tab;
        state.joined = true;
        state.connectionStatus = "connected";
        setUp(state);
        const container = document.createElement("div");
        renderTournament({
            actions: {
                deleteTournament: () => {},
                renameTournament: () => {},
                selectTab: () => {},
                sendChat: () => false,
                setChatOpen: () => {},
                showAllPlayed: () => {},
            },
            config: { ...config, isOwner },
            container,
            state,
            tournamentId: "cup",
        });
        return container;
    }

    test("shows the owner a settings tab with rename and delete and a disabled start game, and nobody else", () => {
        const ownerTournament = renderWith(true, "tournament");
        const ownerSettings = renderWith(true, "settings");
        const player = renderWith(false, "settings");

        expect(ownerTournament.querySelectorAll('[role="tab"]')).toHaveLength(2);
        expect(ownerTournament.querySelector(".tournament-delete")).toBeNull();
        expect(
            ownerTournament.querySelector<HTMLButtonElement>(".tournament-start-game")?.disabled,
        ).toBe(true);
        expect(ownerSettings.querySelector(".tournament-delete")).not.toBeNull();
        expect(ownerSettings.querySelector(".tournament-chat")).toBeNull();
        expect(
            [
                '[role="tab"]',
                ".tournament-delete",
                ".tournament-start-game",
                ".tournament-chat",
            ].map((selector) => player.querySelector(selector) !== null),
        ).toEqual([false, false, false, true]);
    });

    test("shows the five latest ended games with their count and outcomes, the rest behind show all", () => {
        const container = renderWith(false, "tournament", (state) => {
            state.played = [
                {
                    endReason: "abandoned",
                    endedAt: new Date(),
                    gameId: "g6",
                    players: PLAYERS,
                    ranked: null,
                },
                ...["g5", "g4", "g3", "g2", "g1"].map(completedGame),
            ];
        });

        const section = container.querySelector(".tournament-played");
        const rows = [...container.querySelectorAll(".played-game")];
        expect(
            [section?.querySelector("h2"), section?.querySelector(".lobby-table-count")].map(
                squeezedText,
            ),
        ).toEqual(["Game history (6)", "5 completed · 1 abandoned"]);
        expect(rows).toHaveLength(5);
        expect(squeezedText(rows[0]?.querySelector(".played-game-unranked"))).toBe(
            "Abandoned Dave, Carol, Bob, and Alice",
        );
        expect(rows.slice(0, 2).map((row) => row.querySelector("a")?.getAttribute("href"))).toEqual(
            [undefined, "/play/history/g5"],
        );
        expect(
            [...(rows[1]?.querySelectorAll(".games-pts") ?? [])].map((score) => score.textContent),
        ).toEqual(["+5.1", "+2.1", "-0.9", "-3.9"]);
        expect(section?.querySelector(".played-games-more")?.textContent?.trim()).toBe(
            "Show all 6",
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
