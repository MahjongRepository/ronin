import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { type SocketStatus } from "@/lobby-socket";
import { type PageLifetime } from "@/page-lifetime";
import { JOIN_RETRY_DELAY_MS } from "@/room/handlers";

let capturedMessageHandler: ((message: Record<string, unknown>) => void) | null = null;
let capturedStatusHandler: ((status: SocketStatus) => void) | null = null;
let capturedLifetime: PageLifetime | null = null;

const mockConnect = vi.fn();
const mockDisconnect = vi.fn();
const mockSocketCreated = vi.fn();

vi.mock("@/lobby-socket", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/lobby-socket")>()),
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

vi.mock("@/page-lifetime", () => ({
    bindToPageLifetime: (lifetime: PageLifetime) => {
        capturedLifetime = lifetime;
    },
}));

const { initRoomPage } = await import("@/room");

const WS_URL = "ws://lobby/ws/rooms/room-1";

function renderPage(
    attributes = `data-room-name="Jade Crane" data-ws-url="${WS_URL}" data-chat-max-length="1000"`,
    chrome = "",
): HTMLElement {
    document.body.innerHTML = `<div id="room-app" ${attributes}></div>${chrome}`;
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
    mockSocketCreated.mockClear();
    vi.useFakeTimers();
});

afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    sessionStorage.clear();
    document.body.replaceChildren();
    document.documentElement.lang = "";
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

describe("initRoomPage language switch", () => {
    const CHROME = `
        <nav aria-label="Main" data-i18n-aria-label="nav.aria_label">
            <a href="/history" data-i18n="nav.history">History</a>
        </nav>
        <footer>
            <form method="POST" action="/lang" class="footer-lang" aria-label="Language" data-i18n-aria-label="footer.language_label">
                <input type="hidden" name="csrf_token" value="csrf-1">
                <input type="hidden" name="next" value="/rooms/room-1">
                <button type="submit" name="lang" value="en" lang="en" aria-current="true">English</button>
                <button type="submit" name="lang" value="ru" lang="ru">Русский</button>
            </form>
        </footer>`;

    function openSeatedRoom(): HTMLElement {
        document.documentElement.lang = "en";
        const container = renderPage(undefined, CHROME);
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
        return container;
    }

    function stubLanguageSave() {
        const save = vi.fn(async () => ({ ok: false, status: 0, type: "opaqueredirect" }));
        vi.stubGlobal("fetch", save);
        return save;
    }

    function chooseLanguage(locale: string): void {
        document
            .querySelector<HTMLButtonElement>(`.footer-lang button[value="${locale}"]`)
            ?.click();
    }

    function readChrome(): Record<string, unknown> {
        return {
            activeLanguages: [
                ...document.querySelectorAll(".footer-lang [aria-current='true']"),
            ].map((button) => button.textContent),
            history: document.querySelector("[data-i18n='nav.history']")?.textContent,
            lang: document.documentElement.lang,
            languageLabel: document.querySelector(".footer-lang")?.getAttribute("aria-label"),
            navLabel: document.querySelector("nav")?.getAttribute("aria-label"),
            title: document.title,
        };
    }

    function readRoom(container: HTMLElement): Record<string, unknown> {
        return {
            chat: [...container.querySelectorAll(".room-chat-text")].map(
                (line) => line.textContent,
            ),
            seats: [...container.querySelectorAll(".room-player-item")].map((seat) => [
                seat.querySelector(".room-player-name")?.textContent,
                seat.querySelector(".room-player-status")?.getAttribute("aria-label"),
            ]),
            start: container.querySelector(".room-start-btn")?.textContent?.trim(),
            status: statusText(container),
        };
    }

    test("switches the page and its chrome in place, keeping the socket, the seats and the chat", async () => {
        const save = stubLanguageSave();
        const replace = vi.spyOn(window.location, "replace").mockImplementation(() => {});
        const pageUrl = window.location.href;
        const container = openSeatedRoom();

        chooseLanguage("ru");

        expect(readChrome()).toEqual({
            activeLanguages: ["Русский"],
            history: "История",
            lang: "ru",
            languageLabel: "Язык",
            navLabel: "Основное меню",
            title: "Jade Crane · Маджонг Ronin",
        });
        expect(readRoom(container)).toEqual({
            chat: ["You joined the table"],
            seats: [
                ["dev", "Хозяин"],
                ["guest", "Готов"],
            ],
            start: "Начать игру",
            status: "Подключено",
        });
        expect(
            [mockSocketCreated, mockConnect, mockDisconnect].map((mock) => mock.mock.calls.length),
        ).toEqual([1, 1, 0]);
        expect([replace.mock.calls.length, window.location.href]).toEqual([0, pageUrl]);
        await vi.waitFor(() =>
            expect(save).toHaveBeenCalledExactlyOnceWith(new URL("/lang", pageUrl).href, {
                body: new URLSearchParams({ csrf_token: "csrf-1", lang: "ru" }),
                method: "POST",
                redirect: "manual",
            }),
        );
    });
});
