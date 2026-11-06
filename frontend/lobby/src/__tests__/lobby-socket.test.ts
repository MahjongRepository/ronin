import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { LobbySocket } from "@/lobby-socket";

class FakeWebSocket extends EventTarget {
    static readonly OPEN = 1;
    static instances: FakeWebSocket[] = [];
    readyState = 0;
    send = vi.fn();
    close = vi.fn();

    constructor() {
        super();
        FakeWebSocket.instances.push(this);
    }
}

describe("LobbySocket", () => {
    beforeEach(() => {
        FakeWebSocket.instances = [];
        vi.stubGlobal("WebSocket", FakeWebSocket);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    test("keeps the error status when the close that follows an error arrives", () => {
        const statuses: string[] = [];
        const socket = new LobbySocket(vi.fn(), (status) => statuses.push(status));
        socket.connect("ws://test");
        const [ws] = FakeWebSocket.instances;

        ws.dispatchEvent(new Event("error"));
        ws.dispatchEvent(new Event("close"));

        expect(statuses).toEqual(["error"]);
    });

    test("reports whether a message was sent", () => {
        const socket = new LobbySocket(vi.fn(), vi.fn());
        expect(socket.send({ type: "chat" })).toBe(false);

        socket.connect("ws://test");
        const [ws] = FakeWebSocket.instances;
        ws.readyState = FakeWebSocket.OPEN;
        expect(socket.send({ type: "chat" })).toBe(true);

        ws.dispatchEvent(new Event("close"));
        expect(socket.send({ type: "chat" })).toBe(false);
        expect(ws.send).toHaveBeenCalledTimes(1);
    });

    test("closes a socket it replaces with 4100, so the server holds the seat, and a left one with 1000", () => {
        const socket = new LobbySocket(vi.fn(), vi.fn());
        socket.connect("ws://test");
        socket.connect("ws://test");
        socket.disconnect();

        const [replaced, left] = FakeWebSocket.instances;
        expect(replaced.close).toHaveBeenCalledWith(4100);
        expect(left.close).toHaveBeenCalledWith(1000);
    });
});
