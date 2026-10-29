import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { type SocketStatus } from "@/lobby-socket";
import { type PageLifetime } from "@/page-lifetime";
import { JOIN_RETRY_DELAY_MS } from "@/room/handlers";

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
        send = vi.fn();
    },
}));

vi.mock("@/page-lifetime", () => ({
    bindToPageLifetime: (lifetime: PageLifetime) => {
        capturedLifetime = lifetime;
    },
}));

const { initRoomPage } = await import("@/room");

const WS_URL = "ws://lobby/ws/rooms/room-1";

function renderPage(
    attributes = `data-room-name="Jade Crane" data-ws-url="${WS_URL}" data-chat-max-length="1000"`,
): HTMLElement {
    document.body.innerHTML = `<div id="room-app" ${attributes}></div>`;
    const container = document.getElementById("room-app");
    if (!container) {
        throw new Error("missing #room-app");
    }
    initRoomPage(container);
    return container;
}

function receive(message: Record<string, unknown>): void {
    capturedMessageHandler?.(message);
}

function joinAsHost(): void {
    receive({
        can_start: false,
        is_owner: true,
        player_name: "dev",
        players: [{ is_bot: false, is_owner: true, name: "dev", ready: true }],
        type: "room_joined",
    });
}

function refuseWhileTheGameStarts(): void {
    receive({ message: "room_transitioning", type: "error" });
    capturedStatusHandler?.("disconnected");
}

function statusText(container: HTMLElement): string | null | undefined {
    return container.querySelector(".connection-status")?.textContent;
}

function alertText(container: HTMLElement): string {
    return container.querySelector(".lobby-alert")?.textContent?.replace(/\s+/g, " ").trim() ?? "";
}

beforeEach(() => {
    mockConnect.mockClear();
    mockDisconnect.mockClear();
    vi.useFakeTimers();
});

afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    sessionStorage.clear();
    document.body.replaceChildren();
});

describe("initRoomPage", () => {
    test("shows a reload alert instead of a blank page when the page lacks its settings", () => {
        const container = renderPage(`data-room-name="Jade Crane" data-ws-url="${WS_URL}"`);

        expect(alertText(container)).toContain("This table couldn't be loaded.");
        expect(container.querySelector(".lobby-alert a")?.textContent).toBe("Reload");
        expect(mockConnect).not.toHaveBeenCalled();
    });

    test("shows the lost connection with a reload when the retried join fails", () => {
        const container = renderPage();
        refuseWhileTheGameStarts();
        expect(container.querySelector(".lobby-alert")).toBeNull();

        vi.advanceTimersByTime(JOIN_RETRY_DELAY_MS);
        expect(mockConnect).toHaveBeenCalledTimes(2);
        capturedStatusHandler?.("error");

        expect(alertText(container)).toContain("The connection to the table was lost.");
    });

    test.each([
        ["after taking a seat", joinAsHost],
        ["as the join's first and only message", () => {}],
    ])("hands the game session to the game client %s", (_when, before) => {
        const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
        renderPage();
        before();

        receive({
            game_client_url: "/play",
            game_id: "game-1",
            game_ticket: "ticket-1",
            type: "game_starting",
            ws_url: "ws://game/ws",
        });

        expect(JSON.parse(sessionStorage.getItem("game_session:game-1") ?? "null")).toEqual({
            gameTicket: "ticket-1",
            wsUrl: "ws://game/ws",
        });
        expect(replace).toHaveBeenCalledExactlyOnceWith("/play/game-1");
        expect(mockDisconnect).toHaveBeenCalledTimes(1);
    });

    test("stays on the page with a reload when the game start names no game", () => {
        const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
        const container = renderPage();
        joinAsHost();

        receive({ game_ticket: "ticket-1", type: "game_starting", ws_url: "ws://game/ws" });

        expect(replace).not.toHaveBeenCalled();
        expect(alertText(container)).toContain("The game started, but it couldn't be opened.");
        expect(container.querySelector(".lobby-alert a")?.textContent).toBe("Reload");
    });
});

describe("initRoomPage across the back-forward cache", () => {
    test("closes the socket when the page is hidden and takes a seat again when the cache restores it", () => {
        const container = renderPage();
        joinAsHost();

        capturedLifetime?.release();
        expect(mockDisconnect).toHaveBeenCalledTimes(1);

        capturedLifetime?.restore();
        expect(mockConnect).toHaveBeenCalledTimes(2);
        expect(mockConnect).toHaveBeenLastCalledWith(WS_URL);
        expect(statusText(container)).toBe("Connecting…");
        expect(container.querySelector(".room-placeholder")?.textContent).toBe("Taking a seat…");
        expect(container.querySelector(".room-leave-btn, .room-chat-entry")).toBeNull();
    });

    test("drops a join retry pending when the page was hidden, so the restored seat is not taken twice", () => {
        renderPage();
        refuseWhileTheGameStarts();

        capturedLifetime?.release();
        capturedLifetime?.restore();
        joinAsHost();
        vi.advanceTimersByTime(JOIN_RETRY_DELAY_MS);

        expect(mockConnect).toHaveBeenCalledTimes(2);
    });

    test("keeps a page that another tab took over ended when the cache restores it", () => {
        const container = renderPage();
        joinAsHost();
        receive({ message: "replaced_by_new_connection", type: "error" });

        capturedLifetime?.release();
        capturedLifetime?.restore();

        expect(mockConnect).toHaveBeenCalledTimes(1);
        expect(alertText(container)).toContain("open in another tab");
    });
});
