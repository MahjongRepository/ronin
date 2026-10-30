import { encode } from "@msgpack/msgpack";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GameSocket, type SocketHandlers } from "@/shared/websocket/websocket";

class FakeWebSocket {
    static readonly OPEN = 1;
    static created: FakeWebSocket[] = [];

    binaryType = "blob";
    readyState = 0;
    closed = false;
    onopen: ((event: Event) => void) | null = null;
    onmessage: ((event: MessageEvent) => void) | null = null;
    onclose: ((event: CloseEvent) => void) | null = null;
    onerror: ((event: Event) => void) | null = null;

    constructor(readonly url: string) {
        FakeWebSocket.created.push(this);
    }

    open(): void {
        this.readyState = FakeWebSocket.OPEN;
        this.onopen?.(new Event("open"));
    }

    receiveFrame(data: unknown = new ArrayBuffer(0)): void {
        this.onmessage?.(new MessageEvent("message", { data }));
    }

    fail(): void {
        this.onerror?.(new Event("error"));
    }

    close(): void {
        this.closed = true;
    }
}

let socket: GameSocket | null = null;

function connectedSocket(
    closes: [number, string][],
    handlers: Partial<SocketHandlers> = {},
): FakeWebSocket {
    socket = new GameSocket("ws://game/ws/g1", {
        onClose: (code, reason) => closes.push([code, reason]),
        onError: () => {},
        onMessage: () => {},
        onOpen: () => {},
        onUndecodableFrame: () => {},
        ...handlers,
    });
    const [ws] = FakeWebSocket.created;
    ws.open();
    return ws;
}

describe("GameSocket silence watchdog", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        FakeWebSocket.created = [];
        vi.stubGlobal("WebSocket", FakeWebSocket);
    });

    afterEach(() => {
        socket?.disconnect();
        socket = null;
        vi.unstubAllGlobals();
        vi.useRealTimers();
    });

    it("keeps a socket that hears from the server within the limit, reports a longer silence as a close, and never reconnects itself", () => {
        const closes: [number, string][] = [];
        const ws = connectedSocket(closes);

        vi.advanceTimersByTime(60_000);
        ws.receiveFrame();
        vi.advanceTimersByTime(85_000);
        expect([ws.closed, closes]).toEqual([false, []]);

        vi.advanceTimersByTime(10_000);
        expect([ws.closed, closes]).toEqual([true, [[1006, "server_silent"]]]);

        vi.advanceTimersByTime(120_000);
        expect([FakeWebSocket.created.length, closes.length]).toEqual([1, 1]);
    });

    it("waits out the silence limit the client sets, so a longer time control's turn is never taken for a lost connection", () => {
        const closes: [number, string][] = [];
        const ws = connectedSocket(closes);
        socket?.setSilenceLimit(150_000);

        vi.advanceTimersByTime(145_000);
        expect([ws.closed, closes]).toEqual([false, []]);

        vi.advanceTimersByTime(10_000);
        expect([ws.closed, closes]).toEqual([true, [[1006, "server_silent"]]]);
    });

    it("reports the close on the first check after the device wakes from a long sleep", () => {
        const closes: [number, string][] = [];
        const ws = connectedSocket(closes);

        vi.setSystemTime(Date.now() + 120_000);
        vi.advanceTimersByTime(5000);
        expect([ws.closed, closes]).toEqual([true, [[1006, "server_silent"]]]);
    });
});

describe("GameSocket frames", () => {
    beforeEach(() => {
        FakeWebSocket.created = [];
        vi.stubGlobal("WebSocket", FakeWebSocket);
    });

    afterEach(() => {
        socket?.disconnect();
        socket = null;
        vi.unstubAllGlobals();
    });

    it("reports a frame that decodes into no message as undecodable, apart from the browser's socket error", () => {
        const reports: string[] = [];
        const ws = connectedSocket([], {
            onError: (detail) => reports.push(`error: ${detail}`),
            onMessage: (message) => reports.push(`message: ${JSON.stringify(message)}`),
            onUndecodableFrame: (detail) => reports.push(`undecodable: ${detail}`),
        });

        ws.receiveFrame("text");
        ws.receiveFrame(new Uint8Array([193]).buffer);
        ws.receiveFrame(new Uint8Array(encode([1, 2])).buffer);
        ws.receiveFrame(new Uint8Array(encode({ t: 1 })).buffer);
        ws.fail();
        expect(reports).toEqual([
            "undecodable: Received a non-binary frame",
            "undecodable: Failed to decode a MessagePack frame",
            "undecodable: Received a frame that is not a message object",
            'message: {"t":1}',
            "error: WebSocket error",
        ]);
    });
});
