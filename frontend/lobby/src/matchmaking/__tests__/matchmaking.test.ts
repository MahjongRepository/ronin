import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { type SocketStatus } from "@/lobby-socket";
import { type PageLifetime } from "@/page-lifetime";

let capturedMessageHandler: ((message: Record<string, unknown>) => void) | null = null;
let capturedStatusHandler: ((status: SocketStatus) => void) | null = null;
let capturedLifetime: PageLifetime | null = null;

const mockConnect = vi.fn();
const mockDisconnect = vi.fn();

vi.mock("@/lobby-socket", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/lobby-socket")>()),
    LobbySocket: class MockLobbySocket {
        constructor(
            onMessage: (message: Record<string, unknown>) => void,
            onStatusChange: (status: SocketStatus) => void,
        ) {
            capturedMessageHandler = onMessage;
            capturedStatusHandler = onStatusChange;
        }

        connect = mockConnect;
        disconnect = mockDisconnect;
    },
}));

vi.mock("@/page-lifetime", () => ({
    bindToPageLifetime: (lifetime: PageLifetime) => {
        capturedLifetime = lifetime;
    },
}));

const { initMatchmakingPage } = await import("@/matchmaking");

const WS_URL = "ws://lobby/ws/matchmaking";

function renderPage(): HTMLElement {
    document.body.innerHTML = `<div id="matchmaking-app" data-ws-url="${WS_URL}"></div>`;
    const container = query(document.body, "#matchmaking-app");
    initMatchmakingPage(container);
    return container;
}

function query<ElementType extends HTMLElement = HTMLElement>(
    container: HTMLElement,
    selector: string,
): ElementType {
    const element = container.querySelector<ElementType>(selector);
    if (!element) {
        throw new Error(`missing ${selector}`);
    }
    return element;
}

function text(container: HTMLElement, selector: string): string {
    return query(container, selector).textContent?.replace(/\s+/g, " ").trim() ?? "";
}

function actionLabels(container: HTMLElement): string[] {
    return Array.from(
        container.querySelectorAll(".matchmaking-actions a, .matchmaking-actions button"),
        (element) => element.textContent?.trim() ?? "",
    );
}

beforeEach(() => {
    mockConnect.mockClear();
    mockDisconnect.mockClear();
});

afterEach(() => {
    document.documentElement.lang = "";
    vi.restoreAllMocks();
    sessionStorage.clear();
    document.body.replaceChildren();
});

describe("initMatchmakingPage", () => {
    test("shows the players found so far while searching, with Cancel as the only action", () => {
        const container = renderPage();

        capturedMessageHandler?.({ position: 1, queue_size: 1, type: "queue_joined" });
        capturedMessageHandler?.({ queue_size: 2, type: "queue_update" });

        expect(text(container, "h2")).toBe("Finding a match");
        expect(text(container, ".matchmaking-status")).toBe("2 of 4 players found");
        expect(container.querySelectorAll(".lobby-seat.filled")).toHaveLength(2);
        expect(actionLabels(container)).toEqual(["Cancel"]);
    });

    test.each([
        [1, "Найден 1 игрок из 4"],
        [2, "Найдено 2 игрока из 4"],
        [5, "Найдено 5 игроков из 4"],
    ])("counts %i players found with the Russian plural form", (queueSize, status) => {
        document.documentElement.lang = "ru";
        const container = renderPage();

        capturedMessageHandler?.({ queue_size: queueSize, type: "queue_update" });

        expect(text(container, ".matchmaking-status")).toBe(status);
    });

    test("keeps the match_failed ending and offers a retry despite late queue messages and the close", () => {
        const container = renderPage();
        capturedMessageHandler?.({ queue_size: 4, type: "queue_update" });

        capturedMessageHandler?.({ message: "match_failed", type: "error" });
        capturedMessageHandler?.({ position: 3, queue_size: 3, type: "queue_joined" });
        capturedStatusHandler?.("disconnected");

        expect(text(container, "h2")).toBe("Couldn't start the match");
        expect(text(container, ".lobby-alert")).toContain("the game couldn't be started");
        expect(actionLabels(container)).toEqual(["Search again", "Back to lobby"]);
    });

    test("reconnects and returns to searching when Search again is clicked", () => {
        const container = renderPage();
        capturedMessageHandler?.({ message: "match_failed", type: "error" });
        capturedStatusHandler?.("disconnected");

        query<HTMLButtonElement>(container, ".matchmaking-retry").click();
        capturedStatusHandler?.("connected");

        expect(mockConnect).toHaveBeenCalledTimes(2);
        expect(mockConnect).toHaveBeenLastCalledWith(WS_URL);
        expect(text(container, "h2")).toBe("Finding a match");
        expect(text(container, ".matchmaking-status")).toBe("Looking for players…");
    });

    test.each([
        ["already_in_game", "Matchmaking stopped", ["Search again", "Back to lobby"]],
        ["already_in_room", "Matchmaking stopped", ["Back to lobby"]],
        ["match_starting", "Matchmaking stopped", ["Search again", "Back to lobby"]],
        ["replaced_by_new_connection", "Searching in another tab", ["Back to lobby"]],
    ])(
        "ends the search on %s with a terminal heading and a way back instead of Cancel",
        (code, heading, actions) => {
            const container = renderPage();

            capturedMessageHandler?.({ message: code, type: "error" });
            capturedStatusHandler?.("disconnected");

            expect(text(container, "h2")).toBe(heading);
            expect(container.querySelector(".lobby-alert[role=alert]")).not.toBeNull();
            expect(actionLabels(container)).toEqual(actions);
        },
    );

    test("links already_in_room to the table the server names", () => {
        const container = renderPage();

        capturedMessageHandler?.({ message: "already_in_room", room_id: "room 1", type: "error" });

        const link = query<HTMLAnchorElement>(container, ".matchmaking-actions a[href^='/rooms/']");
        expect(link.getAttribute("href")).toBe("/rooms/room%201");
        expect(link.textContent).toBe("Go to your table");
    });

    test("shows a lost connection with a retry after an error that does not end matchmaking", () => {
        const container = renderPage();

        capturedMessageHandler?.({ message: "Invalid message format", type: "error" });
        capturedStatusHandler?.("disconnected");

        expect(text(container, "h2")).toBe("Matchmaking stopped");
        expect(text(container, ".lobby-alert")).toContain("Lost the connection");
        expect(actionLabels(container)).toEqual(["Search again", "Back to lobby"]);
    });

    test.each([
        [
            "after joining the queue",
            () => capturedMessageHandler?.({ queue_size: 4, type: "queue_joined" }),
        ],
        ["as the join's first and only message", () => {}],
    ])(
        "hands the game session to the game client %s and keeps showing the start",
        (_when, before) => {
            const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
            const container = renderPage();
            before();

            capturedMessageHandler?.({
                game_client_url: "/play",
                game_id: "game-1",
                game_ticket: "ticket-1",
                type: "game_starting",
                ws_url: "ws://game/ws",
            });
            capturedMessageHandler?.({ queue_size: 1, type: "queue_update" });
            capturedStatusHandler?.("disconnected");

            expect(JSON.parse(sessionStorage.getItem("game_session:game-1") ?? "null")).toEqual({
                gameTicket: "ticket-1",
                wsUrl: "ws://game/ws",
            });
            expect(replace).toHaveBeenCalledExactlyOnceWith("/play/game-1");
            expect(text(container, "h2")).toBe("Match found");
            expect(text(container, ".matchmaking-status")).toBe("Starting the game…");
        },
    );

    test("stops with a retry instead of leaving for a missing game when the start names none", () => {
        const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
        const container = renderPage();

        capturedMessageHandler?.({
            game_ticket: "ticket-1",
            type: "game_starting",
            ws_url: "ws://game/ws",
        });

        expect(replace).not.toHaveBeenCalled();
        expect(text(container, "h2")).toBe("Matchmaking stopped");
        expect(actionLabels(container)).toEqual(["Search again", "Back to lobby"]);
    });
});

describe("initMatchmakingPage across the back-forward cache", () => {
    test("closes the socket when the page is hidden and requeues when the back-forward cache restores it", () => {
        const container = renderPage();
        capturedMessageHandler?.({ position: 1, queue_size: 1, type: "queue_joined" });

        capturedLifetime?.release();
        expect(mockDisconnect).toHaveBeenCalledTimes(1);

        capturedLifetime?.restore();
        expect(mockConnect).toHaveBeenCalledTimes(2);
        expect(text(container, ".matchmaking-status")).toBe("Looking for players…");
    });

    test("keeps an ended search ended when the back-forward cache restores the page", () => {
        const container = renderPage();
        capturedMessageHandler?.({ message: "replaced_by_new_connection", type: "error" });

        capturedLifetime?.release();
        capturedLifetime?.restore();

        expect(mockConnect).toHaveBeenCalledTimes(1);
        expect(text(container, "h2")).toBe("Searching in another tab");
    });
});
