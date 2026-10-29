import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONNECTION_STATUS, type ConnectionStatus } from "@/shared/protocol";
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

function connectedSocket(statuses: ConnectionStatus[]): FakeWebSocket {
    socket = new GameSocket(
        () => {},
        (status) => statuses.push(status),
    );
    socket.enableReconnect("ws://game/ws/g1");
    socket.connect("ws://game/ws/g1");
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

    it("keeps a socket that hears from the server within the limit and drops it after a longer silence", () => {
        const statuses: ConnectionStatus[] = [];
        const ws = connectedSocket(statuses);

        vi.advanceTimersByTime(60_000);
        ws.receiveFrame();
        vi.advanceTimersByTime(85_000);
        expect([ws.closed, statuses.at(-1)]).toEqual([false, CONNECTION_STATUS.CONNECTED]);

        vi.advanceTimersByTime(10_000);
        expect([ws.closed, statuses.at(-1)]).toEqual([true, CONNECTION_STATUS.DISCONNECTED]);

        vi.advanceTimersByTime(1000);
        expect(FakeWebSocket.created).toHaveLength(2);
    });

    it("drops the socket on the first check after the device wakes from a long sleep", () => {
        const statuses: ConnectionStatus[] = [];
        const ws = connectedSocket(statuses);

        vi.setSystemTime(Date.now() + 120_000);
        vi.advanceTimersByTime(5000);
        expect([ws.closed, statuses.at(-1)]).toEqual([true, CONNECTION_STATUS.DISCONNECTED]);
    });
});
