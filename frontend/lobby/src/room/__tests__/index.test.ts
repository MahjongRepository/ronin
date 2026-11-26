import { switchLocale } from "@ronin/shared/locale-switch";
import { type MountedView } from "@ronin/shared/router";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type * as LobbySocketModule from "@/lobby-socket";
import { type SocketStatus } from "@/lobby-socket";
import type * as PageLifetimeModule from "@/page-lifetime";
import { type PageLifetime } from "@/page-lifetime";
import { JOIN_RETRY_DELAY_MS } from "@/room/handlers";

let capturedMessageHandler: ((message: Record<string, unknown>) => void) | null = null;
let capturedStatusHandler: ((status: SocketStatus) => void) | null = null;
let capturedLifetime: PageLifetime | null = null;

const mockConnect = vi.fn();
const mockDisconnect = vi.fn();
const mockSocketCreated = vi.fn();

vi.mock("@/lobby-socket", async (importOriginal) => ({
    ...(await importOriginal<typeof LobbySocketModule>()),
    LobbySocket: class MockLobbySocket {
        constructor(
            onMessage: (message: Record<string, unknown>) => void,
            onStatusChange: (status: SocketStatus) => void,
        ) {
            capturedMessageHandler = onMessage;
            capturedStatusHandler = onStatusChange;
            mockSocketCreated();
        }

        connect = mockConnect;
        disconnect = mockDisconnect;
        send = vi.fn();
    },
}));

vi.mock("@/page-lifetime", async (importOriginal) => {
    const actual = await importOriginal<typeof PageLifetimeModule>();
    return {
        ...actual,
        bindToPageLifetime: (lifetime: PageLifetime) => {
            capturedLifetime = lifetime;
            return actual.bindToPageLifetime(lifetime);
        },
    };
});

const { mountRoomView } = await import("@/room");

const WS_URL = "ws://lobby/ws/rooms/room-1";
const ROOM_CONFIG = { chat_max_length: 1000, room_name: "Jade Crane", ws_url: WS_URL };

const navigate = vi.fn();
let mounted: MountedView | null = null;

function answerRoomConfig(status: number, body: unknown): void {
    vi.stubGlobal(
        "fetch",
        vi.fn(async () => Response.json(body, { status })),
    );
}

function mountRoom(): HTMLElement {
    const host = document.createElement("main");
    document.body.append(host);
    mounted = mountRoomView(host, "room-1", { navigate });
    return host;
}

async function openRoom(body: unknown = ROOM_CONFIG): Promise<HTMLElement> {
    answerRoomConfig(200, body);
    const host = mountRoom();
    await vi.waitFor(() =>
        expect(
            mockSocketCreated.mock.calls.length + host.querySelectorAll(".lobby-alert").length,
        ).toBe(1),
    );
    return host;
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
    return container.querySelector(".connection-status-label")?.textContent;
}

function alertText(container: HTMLElement): string {
    return container.querySelector(".lobby-alert")?.textContent?.replace(/\s+/g, " ").trim() ?? "";
}

function readRoom(container: HTMLElement): Record<string, unknown> {
    return {
        chat: [...container.querySelectorAll(".room-chat-text")].map((line) => line.textContent),
        seats: [...container.querySelectorAll(".room-player-item")].map((seat) => [
            seat.querySelector(".room-player-name")?.textContent,
            seat.querySelector(".room-player-status")?.getAttribute("aria-label"),
        ]),
        start: container.querySelector(".room-start-btn")?.textContent?.trim(),
        status: statusText(container),
        title: document.title,
    };
}

beforeEach(() => {
    mockConnect.mockClear();
    mockDisconnect.mockClear();
    mockSocketCreated.mockClear();
    navigate.mockClear();
    vi.useFakeTimers();
});

afterEach(() => {
    mounted?.unmount();
    mounted = null;
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    sessionStorage.clear();
    document.body.replaceChildren();
    document.documentElement.lang = "";
    document.cookie = "lang=; Path=/; Max-Age=0";
});

describe("mountRoomView", () => {
    test("shows a reload alert instead of a blank page when the room config is invalid", async () => {
        const host = await openRoom({ room_name: "Jade Crane", ws_url: WS_URL });

        expect(alertText(host)).toContain("This table couldn't be loaded.");
        expect(host.querySelector(".lobby-alert a")?.textContent).toBe("Reload");
        expect(mockSocketCreated).not.toHaveBeenCalled();
    });

    test.each([
        { gameUrl: "/play/game-1", navigated: [], replaced: [["/play/game-1"]] },
        {
            gameUrl: null,
            navigated: [["/?notice=table_gone", { replace: true }]],
            replaced: [],
        },
    ])(
        "leaves a room that is gone for its game page or else the lobby notice (game_url $gameUrl)",
        async ({ gameUrl, navigated, replaced }) => {
            const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
            answerRoomConfig(404, { error: "room_not_found", game_url: gameUrl });

            mountRoom();
            await vi.waitFor(() =>
                expect(replace.mock.calls.length + navigate.mock.calls.length).toBe(1),
            );

            expect([replace.mock.calls, navigate.mock.calls]).toEqual([replaced, navigated]);
            expect(mockSocketCreated).not.toHaveBeenCalled();
        },
    );

    test("opens no socket when unmounted before the room config arrives", async () => {
        answerRoomConfig(200, ROOM_CONFIG);
        const host = mountRoom();

        mounted?.unmount();
        await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
        await vi.advanceTimersByTimeAsync(0);

        expect(mockSocketCreated).not.toHaveBeenCalled();
        expect(host.querySelector(".room h2")?.textContent).toBe("Table");
    });

    test("closes the socket on unmount and a later online event does not reconnect", async () => {
        await openRoom();
        capturedStatusHandler?.("connected");
        joinAsHost();

        mounted?.unmount();
        window.dispatchEvent(new Event("online"));
        vi.runOnlyPendingTimers();

        expect(mockDisconnect).toHaveBeenCalledTimes(1);
        expect(mockConnect).toHaveBeenCalledTimes(1);
    });

    test("shows the lost connection with a reload when the retried join fails", async () => {
        const host = await openRoom();
        refuseWhileTheGameStarts();
        expect(host.querySelector(".lobby-alert")).toBeNull();

        vi.advanceTimersByTime(JOIN_RETRY_DELAY_MS);
        expect(mockConnect).toHaveBeenCalledTimes(2);
        capturedStatusHandler?.("error");

        expect(alertText(host)).toContain("The connection to the table was lost.");
    });

    test.each([
        ["after taking a seat", joinAsHost],
        ["as the join's first and only message", () => {}],
    ])(
        "hands the game session to the game client %s and stays out of the room when the back-forward cache restores the page",
        async (_when, before) => {
            const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
            await openRoom();
            before();

            receive({
                game_client_url: "/play",
                game_id: "game-1",
                game_ticket: "ticket-1",
                seat_version: 2,
                type: "game_starting",
                ws_url: "ws://game/ws",
            });

            expect(JSON.parse(sessionStorage.getItem("game_session:game-1") ?? "null")).toEqual({
                claimId: expect.any(String),
                gameTicket: "ticket-1",
                seatVersion: 2,
                wsUrl: "ws://game/ws",
            });
            expect(replace).toHaveBeenCalledExactlyOnceWith("/play/game-1");
            expect(mockDisconnect).toHaveBeenCalledTimes(1);

            window.dispatchEvent(Object.assign(new Event("pageshow"), { persisted: true }));

            expect(mockConnect).toHaveBeenCalledTimes(1);
        },
    );

    test("stays on the page with a reload when the game start names no game", async () => {
        const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
        const host = await openRoom();
        joinAsHost();

        receive({ game_ticket: "ticket-1", type: "game_starting", ws_url: "ws://game/ws" });

        expect(replace).not.toHaveBeenCalled();
        expect(alertText(host)).toContain("The game started, but it couldn't be opened.");
        expect(host.querySelector(".lobby-alert a")?.textContent).toBe("Reload");
    });
});

describe("mountRoomView across the back-forward cache", () => {
    test("closes the socket when the page is hidden and takes a seat again when the cache restores it", async () => {
        const host = await openRoom();
        joinAsHost();

        capturedLifetime?.release();
        expect(mockDisconnect).toHaveBeenCalledTimes(1);

        capturedLifetime?.restore();
        expect(mockConnect).toHaveBeenCalledTimes(2);
        expect(mockConnect).toHaveBeenLastCalledWith(WS_URL);
        expect(statusText(host)).toBe("Connecting…");
        expect(host.querySelector(".room-player-name")?.textContent).toBe("Taking a seat…");
        expect(host.querySelector(".room-player-item.me, .room-chat-entry")).toBeNull();
    });

    test("drops a join retry pending when the page was hidden, so the restored seat is not taken twice", async () => {
        await openRoom();
        refuseWhileTheGameStarts();

        capturedLifetime?.release();
        capturedLifetime?.restore();
        joinAsHost();
        vi.advanceTimersByTime(JOIN_RETRY_DELAY_MS);

        expect(mockConnect).toHaveBeenCalledTimes(2);
    });

    test("keeps a page that another tab took over ended when the cache restores it", async () => {
        const host = await openRoom();
        joinAsHost();
        receive({ message: "replaced_by_new_connection", type: "error" });

        capturedLifetime?.release();
        capturedLifetime?.restore();

        expect(mockConnect).toHaveBeenCalledTimes(1);
        expect(alertText(host)).toContain("open in another tab");
    });
});

describe("mountRoomView language switch", () => {
    test("re-renders the seated room in the new language, keeping the socket, the seats and the chat", async () => {
        document.documentElement.lang = "en";
        const host = await openRoom();
        capturedStatusHandler?.("connected");
        receive({
            can_start: true,
            is_owner: true,
            player_name: "dev",
            players: [
                { is_bot: false, is_owner: true, name: "dev", ready: true },
                { is_bot: false, is_owner: false, name: "guest", ready: true },
            ],
            type: "room_joined",
        });

        switchLocale("ru");
        mounted?.rerender();

        expect(readRoom(host)).toEqual({
            chat: ["You joined the table"],
            seats: [
                ["dev", "Хозяин"],
                ["guest", "Готов"],
            ],
            start: "Начать игру",
            status: "Подключено",
            title: "Jade Crane · Ronin Beta",
        });
        expect(
            [mockSocketCreated, mockConnect, mockDisconnect].map((mock) => mock.mock.calls.length),
        ).toEqual([1, 1, 0]);
    });
});
