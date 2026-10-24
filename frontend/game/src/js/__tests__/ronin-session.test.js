import { decode, encode } from "@msgpack/msgpack";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RoninSession from "../ronin/session.js";

class FakeWebSocket {
    static OPEN = 1;
    static created = [];

    constructor(url) {
        this.url = url;
        this.readyState = 0;
        this.sent = [];
        this.closed = false;
        FakeWebSocket.created.push(this);
    }

    send(bytes) {
        this.sent.push(decode(bytes));
    }

    close() {
        this.closed = true;
    }

    open() {
        this.readyState = FakeWebSocket.OPEN;
        this.onopen();
    }

    receive(message) {
        const bytes = encode(message);
        this.onmessage({
            data: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
        });
    }

    drop() {
        this.readyState = 3;
        this.onclose();
    }
}

const latestSocket = () => FakeWebSocket.created.at(-1);
const JOIN = { t: 7, game_ticket: "ticket" };
const RECONNECT = { t: 6, game_ticket: "ticket" };
const ROUND_STARTED = { t: 9, s: 0 };

function connectSession() {
    const events = [];
    const session = new RoninSession({
        wsUrl: "ws://game/ws/g",
        gameId: "g",
        gameTicket: "ticket",
        onEvent: (message) => events.push(message),
    });
    session.connect();
    latestSocket().open();
    return { session, events };
}

describe("RoninSession", () => {
    let session;

    beforeEach(() => {
        vi.useFakeTimers();
        FakeWebSocket.created = [];
        vi.stubGlobal("WebSocket", FakeWebSocket);
    });

    afterEach(() => {
        session?.close();
        session = null;
        vi.unstubAllGlobals();
        vi.useRealTimers();
    });

    it("sends nothing on its own while the server is busy with other seats", () => {
        ({ session } = connectSession());
        const ws = latestSocket();

        for (let second = 0; second < 80; second += 20) {
            vi.advanceTimersByTime(20_000);
            ws.receive(ROUND_STARTED);
        }

        expect(ws.sent).toEqual([JOIN]);
        expect(FakeWebSocket.created).toHaveLength(1);
    });

    it("treats a server silent past any legitimate wait as a drop and resumes the seat", () => {
        ({ session } = connectSession());
        const first = latestSocket();
        first.receive(ROUND_STARTED);

        vi.advanceTimersByTime(85_000);
        expect(first.closed).toBe(false);
        vi.advanceTimersByTime(10_000);
        expect(first.closed).toBe(true);
        vi.advanceTimersByTime(1_000);
        latestSocket().open();

        expect(FakeWebSocket.created).toHaveLength(2);
        expect(latestSocket().sent).toEqual([RECONNECT]);
    });

    it("switches to RECONNECT for a started game and retries a reconnect the server is not ready for", () => {
        ({ session } = connectSession());
        const ws = latestSocket();

        ws.receive({ type: "session_error", code: "join_game_already_started", message: "" });
        ws.receive({ type: "session_error", code: "reconnect_retry_later", message: "" });
        vi.advanceTimersByTime(1_000);

        expect(ws.sent).toEqual([JOIN, RECONNECT, RECONNECT]);
        expect(FakeWebSocket.created).toHaveLength(1);
    });

    it("stays closed once the game has ended", () => {
        let events;
        ({ session, events } = connectSession());

        latestSocket().receive({ t: 10, ws: 0, st: [] });
        latestSocket().drop();
        vi.advanceTimersByTime(60_000);

        expect(events).toHaveLength(1);
        expect(FakeWebSocket.created).toHaveLength(1);
    });
});
