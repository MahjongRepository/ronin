import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GameSocket } from "@/shared/websocket/websocket";

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

    receiveFrame(): void {
        this.onmessage?.(new MessageEvent("message", { data: new ArrayBuffer(0) }));
    }

    close(): void {
        this.closed = true;
    }
}

let socket: GameSocket | null = null;

function connectedSocket(closes: [number, string][]): FakeWebSocket {
    socket = new GameSocket("ws://game/ws/g1", {
        onClose: (code, reason) => closes.push([code, reason]),
        onError: () => {},
        onMessage: () => {},
        onOpen: () => {},
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

    it("reports the close on the first check after the device wakes from a long sleep", () => {
        const closes: [number, string][] = [];
        const ws = connectedSocket(closes);

        vi.setSystemTime(Date.now() + 120_000);
        vi.advanceTimersByTime(5000);
        expect([ws.closed, closes]).toEqual([true, [[1006, "server_silent"]]]);
    });
});
