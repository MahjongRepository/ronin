import { afterEach, describe, expect, test, vi } from "vitest";

import { t } from "@/i18n";
import {
    TOURNAMENT_ERROR_CODES,
    buildMessageHandlers,
    buildStatusHandler,
    describeTournamentError,
    handleMessage,
    rejoinOnPageShow,
} from "@/tournament/handlers";
import { type PlayedGame } from "@/tournament/played-games";
import {
    TOURNAMENT_NOT_FOUND,
    type TournamentState,
    type TournamentTab,
    createTournamentState,
    isConnectionLost,
    readTournamentConfigAnswer,
} from "@/tournament/state";
import { renderTournament } from "@/tournament/ui";

function buildTournament() {
    const state = createTournamentState();
    const handlers = buildMessageHandlers(state, vi.fn(), vi.fn());
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
                    finishTournament: () => {},
                    renameTournament: () => {},
                    returnToGame: () => {},
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
        ranked: PLAYERS.map((name, index) => ({
            finalScore: 5.1 - index * 3,
            name,
            place: index + 1,
        })),
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
        const handlers = buildMessageHandlers(state, vi.fn(), vi.fn());
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
                { final_score: 200, name: "Bob", place: 1, score: 40_000, seat: 2 },
                { final_score: 200, name: "Dave", place: 1, score: 40_000, seat: 0 },
                { final_score: -110, name: "Alice", place: 3, score: 24_000, seat: 3 },
                { final_score: -290, name: "Carol", place: 4, score: 16_000, seat: 1 },
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
                    { finalScore: 20, name: "Bob", place: 1 },
                    { finalScore: 20, name: "Dave", place: 1 },
                    { finalScore: -11, name: "Alice", place: 3 },
                    { finalScore: -29, name: "Carol", place: 4 },
                ],
            ],
        ]);
    });

    test("keeps the current games from the join, adds started ones and drops ended ones", () => {
        const state = createTournamentState();
        const handlers = buildMessageHandlers(state, vi.fn(), vi.fn());
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

function joinFinishingTournament() {
    const state = createTournamentState();
    const reload = vi.fn();
    const handlers = buildMessageHandlers(state, vi.fn(), reload);
    handleMessage(handlers, { players: ["Alice"], type: "joined" });
    state.connectionStatus = "connected";
    return { handlers, reload, state };
}

describe("a finished tournament", () => {
    test("stops reconnecting, reloads once and keeps only the game history when the owner finishes it", () => {
        const { handlers, reload, state } = joinFinishingTournament();
        const { container, render } = mountPage(state);

        handleMessage(handlers, { message: "tournament_finished", type: "error" });
        buildStatusHandler(state, render, vi.fn())("disconnected");

        expect(reload).toHaveBeenCalledOnce();
        expect(state.reconnectTimer).toBeNull();
        expect(
            [".tournament-current", ".tournament-online", ".tournament-chat", "[role=alert]"].map(
                (selector) => container.querySelector(selector) !== null,
            ),
        ).toEqual([false, false, false, false]);
        expect(container.querySelector(".tournament-played")).not.toBeNull();
        expect(container.querySelector(".tournament-finished")).not.toBeNull();
    });

    test("reads its finish and ended games from the config", () => {
        const answer = readTournamentConfigAnswer({
            data: {
                chat_max_length: 100,
                finished_at: 1_800_000_000,
                is_owner: false,
                name: "Cup",
                name_max_length: 80,
                played: [
                    {
                        end_reason: "abandoned",
                        ended_at: 1_799_999_000,
                        game_id: "g1",
                        players: PLAYERS,
                        result: [],
                    },
                ],
                ws_url: "wss://ronin.test/ws/tournaments/cup",
            },
            ok: true,
        });

        const finish = answer.kind === "open" ? answer.config.finish : undefined;
        expect(finish?.finishedAt).toEqual(new Date(1_800_000_000 * 1000));
        expect(finish?.played.map((game) => game.gameId)).toEqual(["g1"]);
    });
});

describe("buildStatusHandler", () => {
    afterEach(() => {
        vi.useRealTimers();
    });

    test("keeps the page in place behind a connecting status while a lost socket waits to reconnect", () => {
        vi.useFakeTimers();
        const { state } = buildTournament();
        const rejoin = vi.fn();
        const { container, render } = mountPage(state);

        buildStatusHandler(state, render, rejoin)("disconnected");

        expect(state.reconnectTimer).not.toBeNull();
        expect(rejoin).not.toHaveBeenCalled();
        expect(container.querySelector(".tournament-online")).not.toBeNull();
        expect(container.querySelector(".tournament-played")).not.toBeNull();
        expect(
            container.querySelector(".tournament-header [role=status] .connection-status-label")
                ?.textContent,
        ).toBe("Connecting…");
    });
});

describe("rejoinOnPageShow", () => {
    test("keeps the way back into a live game while the restored page rejoins", () => {
        const { state } = buildTournament();
        state.liveGame.playing = true;
        const rejoin = vi.fn();

        rejoinOnPageShow(state, rejoin);

        expect(rejoin).toHaveBeenCalledOnce();
        expect(state.joined).toBe(false);
        expect(state.liveGame.playing).toBe(true);
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
        finish: null,
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
                finishTournament: () => {},
                renameTournament: () => {},
                returnToGame: () => {},
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

    test("offers a player of a live game the way back into it, on a finished tournament too", () => {
        const finished = renderWith(false, "tournament", (state) => {
            state.finishedAt = new Date(1_800_000_000 * 1000);
            state.liveGame.playing = true;
        });
        const notPlaying = renderWith(false, "tournament");

        expect(finished.querySelector(".tournament-return-btn")?.textContent?.trim()).toBe(
            "Return to your game",
        );
        expect(notPlaying.querySelector(".tournament-return-btn")).toBeNull();
    });

    test("holds a loading placeholder in both game sections until the join answers", () => {
        const container = renderWith(false, "tournament", (state) => {
            state.joined = false;
            state.connectionStatus = "connecting";
        });

        expect(
            [".tournament-current", ".tournament-played"].map(
                (section) =>
                    container.querySelector(`${section} .list-loading[role=status]`) !== null,
            ),
        ).toEqual([true, true]);
        expect(container.querySelector(".tournament-side")).toBeNull();
        expect(container.querySelector(".tournament-page--entering")).not.toBeNull();
        expect(
            renderWith(false, "tournament").querySelector(".tournament-page--entering"),
        ).toBeNull();
    });

    test("names the page only once the config loads, and the fallback only for a page error", () => {
        const state = createTournamentState();
        const page = mountPage(state);
        page.render();
        const loadingName = squeezedText(page.container.querySelector(".tournament-name"));

        state.pageError = TOURNAMENT_NOT_FOUND;
        page.render();

        expect(loadingName).toBe("");
        expect(squeezedText(page.container.querySelector(".tournament-name"))).toBe(
            t("tournament.fallback_name"),
        );
        expect(page.container.querySelector(".tournament-page--entering")).toBeNull();
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
