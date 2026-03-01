import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { CLIENT_MESSAGE_TYPE, GAME_ACTION } from "@/shared/protocol";

// --- Mocks ---

let capturedMessageHandler: ((message: Record<string, unknown>) => void) | null = null;
let capturedStatusHandler: ((status: string) => void) | null = null;

const mockSend = vi.fn();
const mockConnect = vi.fn();
const mockEnableReconnect = vi.fn();
const mockDisableReconnect = vi.fn();
const mockDisconnect = vi.fn();

// Use a class mock so `new GameSocket(...)` works correctly
vi.mock("@/websocket", () => ({
    GameSocket: class MockGameSocket {
        constructor(
            onMessage: (msg: Record<string, unknown>) => void,
            onStatusChange: (s: string) => void,
        ) {
            capturedMessageHandler = onMessage;
            capturedStatusHandler = onStatusChange;
        }

        connect = mockConnect;
        disableReconnect = mockDisableReconnect;
        disconnect = mockDisconnect;
        enableReconnect = mockEnableReconnect;
        isOpen = true;
        send = mockSend;
    },
}));

vi.mock("@/session-storage", () => ({
    clearGameSession: vi.fn(),
    clearSessionData: vi.fn(),
    getGameSession: vi.fn().mockReturnValue({ gameTicket: "ticket-123", wsUrl: "ws://test" }),
}));

vi.mock("@/env", () => ({
    getLobbyUrl: vi.fn().mockReturnValue("/lobby"),
}));

vi.mock("lit-html", () => ({
    html: (..._args: unknown[]) => ({ _brand: "template" }),
    render: vi.fn(),
}));

// Dynamic import after mocks are set up (vitest hoists vi.mock calls)
const { cleanupGameView, gameView } = await import("@/views/game");

let locationReplace = vi.fn();

function resetMocks(): void {
    capturedMessageHandler = null;
    capturedStatusHandler = null;
    mockSend.mockClear();
    mockConnect.mockClear();
    mockEnableReconnect.mockClear();
    mockDisableReconnect.mockClear();
    mockDisconnect.mockClear();
}

function setupLocation(): void {
    locationReplace = vi.fn();
    Object.defineProperty(window, "location", {
        configurable: true,
        value: { replace: locationReplace },
        writable: true,
    });
}

/** Set up a connected game view with captured message/status handlers. */
function setupConnection(): void {
    gameView("test-game");
    vi.runAllTimers();
    capturedStatusHandler!("connected");
}

const retryLaterMessage = {
    code: "reconnect_retry_later",
    message: "Try again later",
    type: "session_error",
};

/** Transition connection to "playing" state and simulate a reconnect scenario. */
function setupPlayingAndReconnect(): void {
    setupConnection();
    capturedMessageHandler!({ d: 0, t: 1 });
    capturedStatusHandler!("disconnected");
    capturedStatusHandler!("connected");
    mockSend.mockClear();
}

describe("game view message handling", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        resetMocks();
        setupLocation();
        cleanupGameView();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    describe("connection lifecycle", () => {
        test("sends JOIN_GAME on initial connection", () => {
            setupConnection();
            expect(mockSend).toHaveBeenCalledWith(
                expect.objectContaining({
                    game_ticket: "ticket-123",
                    t: CLIENT_MESSAGE_TYPE.JOIN_GAME,
                }),
            );
        });

        test("join -> playing: reconnect sends RECONNECT not JOIN_GAME", () => {
            setupConnection();
            mockSend.mockClear();

            capturedMessageHandler!({ d: 0, t: 1 });
            capturedStatusHandler!("disconnected");
            capturedStatusHandler!("connected");

            expect(mockSend).toHaveBeenCalledWith(
                expect.objectContaining({
                    game_ticket: "ticket-123",
                    t: CLIENT_MESSAGE_TYPE.RECONNECT,
                }),
            );
            expect(mockSend).not.toHaveBeenCalledWith(
                expect.objectContaining({ t: CLIENT_MESSAGE_TYPE.JOIN_GAME }),
            );
        });

        test("game_reconnected is processed without redirect", () => {
            setupPlayingAndReconnect();

            capturedMessageHandler!({
                cp: 0,
                dc: [1, 2],
                dd: [
                    [1, 2],
                    [3, 4],
                ],
                di: [0],
                dl: 0,
                gid: "test-game",
                h: 0,
                mt: [0, 1, 2],
                n: 1,
                p: [
                    { ai: 0, nm: "P1", s: 0 },
                    { ai: 0, nm: "P2", s: 1 },
                    { ai: 1, nm: "B1", s: 2 },
                    { ai: 1, nm: "B2", s: 3 },
                ],
                pst: [],
                r: 0,
                s: 0,
                tr: 70,
                type: "game_reconnected",
                w: 0,
            });

            expect(locationReplace).not.toHaveBeenCalled();
        });
    });

    describe("reconnection", () => {
        test("permanent reconnect error triggers redirect", () => {
            setupConnection();
            capturedMessageHandler!({ d: 0, t: 1 });

            capturedMessageHandler!({
                code: "reconnect_game_gone",
                message: "Game no longer exists",
                type: "session_error",
            });

            expect(locationReplace).toHaveBeenCalledWith("/lobby");
        });

        test("reconnect_retry_later schedules retry", () => {
            setupPlayingAndReconnect();

            capturedMessageHandler!(retryLaterMessage);

            expect(locationReplace).not.toHaveBeenCalled();
            vi.advanceTimersByTime(1500);
            expect(mockSend).toHaveBeenCalledWith(
                expect.objectContaining({ t: CLIENT_MESSAGE_TYPE.RECONNECT }),
            );
        });

        test("reconnect_retry_later uses exponential backoff", () => {
            setupPlayingAndReconnect();

            function expectRetryAfterMs(delayMs: number): void {
                capturedMessageHandler!(retryLaterMessage);
                vi.advanceTimersByTime(delayMs - 1);
                expect(mockSend).not.toHaveBeenCalled();
                vi.advanceTimersByTime(1);
                expect(mockSend).toHaveBeenCalledTimes(1);
                mockSend.mockClear();
            }

            expectRetryAfterMs(1000);
            expectRetryAfterMs(2000);
        });
    });

    describe("session errors", () => {
        test("not_in_game triggers redirect to lobby", () => {
            setupConnection();
            capturedMessageHandler!({ d: 0, t: 1 });

            capturedMessageHandler!({
                code: "not_in_game",
                message: "Player is not in a game",
                type: "session_error",
            });

            expect(locationReplace).toHaveBeenCalledWith("/lobby");
        });

        test("join_game_already_started sends RECONNECT", () => {
            setupConnection();
            mockSend.mockClear();

            capturedMessageHandler!({
                code: "join_game_already_started",
                message: "Game already started",
                type: "session_error",
            });

            expect(mockSend).toHaveBeenCalledWith(
                expect.objectContaining({ t: CLIENT_MESSAGE_TYPE.RECONNECT }),
            );
            expect(locationReplace).not.toHaveBeenCalled();
        });
    });

    describe("game events", () => {
        test("round end triggers auto-confirm after delay", () => {
            setupConnection();
            mockSend.mockClear();

            capturedMessageHandler!({
                ct: [0, 4, 8],
                hr: { fu: 30, han: 3, yk: [{ han: 1, yi: 0 }] },
                ml: [],
                rc: 0,
                rt: 0,
                sch: { "0": 30, "1": -10, "2": -10, "3": -10 },
                scs: { "0": 280, "1": 240, "2": 240, "3": 240 },
                t: 4,
                ws: 0,
                wt: 12,
            });

            expect(mockSend).not.toHaveBeenCalled();
            vi.advanceTimersByTime(1500);
            expect(mockSend).toHaveBeenCalledWith(
                expect.objectContaining({
                    a: GAME_ACTION.CONFIRM_ROUND,
                    t: CLIENT_MESSAGE_TYPE.GAME_ACTION,
                }),
            );
        });

        test("parse failure logs fallback without crashing", () => {
            setupConnection();

            capturedMessageHandler!({ t: 8 });
            expect(locationReplace).not.toHaveBeenCalled();

            capturedMessageHandler!({ d: 0, t: 1 });
            expect(locationReplace).not.toHaveBeenCalled();
        });
    });
});
