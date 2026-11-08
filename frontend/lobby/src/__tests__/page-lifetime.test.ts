import { afterEach, describe, expect, it, vi } from "vitest";

import { LobbySocket } from "@/lobby-socket";
import { bindToPageLifetime } from "@/page-lifetime";

class FakeWebSocket extends EventTarget {
    static instances: FakeWebSocket[] = [];
    close = vi.fn();

    constructor() {
        super();
        FakeWebSocket.instances.push(this);
    }
}

function openBoundSocket(statuses: string[]): FakeWebSocket {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const socket = new LobbySocket(vi.fn(), (status) => statuses.push(status));
    socket.connect("ws://test");
    bindToPageLifetime({ release: () => socket.disconnect(), restore: vi.fn() });
    const [ws] = FakeWebSocket.instances;
    return ws;
}

describe("bindToPageLifetime", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("releases the socket once a navigation starts, so the browser aborting it for that navigation reports no lost connection", () => {
        const statuses: string[] = [];
        const ws = openBoundSocket(statuses);

        window.dispatchEvent(new Event("beforeunload"));
        ws.dispatchEvent(new Event("error"));
        ws.dispatchEvent(new Event("close"));

        expect(ws.close).toHaveBeenCalledWith(1000);
        expect(statuses).toEqual([]);
    });
});
