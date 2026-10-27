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

    drop(code = 1006) {
        this.readyState = 3;
        this.onclose({ code, reason: "" });
    }
}

const latestSocket = () => FakeWebSocket.created.at(-1);
const JOIN = { t: 7, game_ticket: "ticket" };
const RECONNECT = { t: 6, game_ticket: "ticket" };
const ROUND_STARTED = { t: 9, s: 0 };

function connectSession() {
    const events = [];
    const drops = [];
    const session = new RoninSession({
        wsUrl: "ws://game/ws/g",
        gameId: "g",
        gameTicket: "ticket",
        onEvent: (message) => events.push(message),
        onDisconnected: () => drops.push("drop"),
    });
    session.connect();
    latestSocket().open();
    return { session, events, drops };
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

    it.each([
        ["another connection took the seat over", 4002],
        ["the server kicked the seat for an impossible action", 1008],
    ])(
        "leaves for the lobby without reconnecting when %s, cancelling a scheduled reconnect retry",
        (_, code) => {
            sessionStorage.setItem("game_session:g", "{}");
            ({ session } = connectSession());
            const ws = latestSocket();
            ws.receive({ type: "session_error", code: "join_game_already_started", message: "" });
            ws.receive({ type: "session_error", code: "reconnect_retry_later", message: "" });

            ws.drop(code);
            vi.advanceTimersByTime(60_000);

            expect(ws.sent).toEqual([JOIN, RECONNECT]);
            expect(FakeWebSocket.created).toHaveLength(1);
            expect(sessionStorage.getItem("game_session:g")).toBeNull();
        },
    );

    it.each([
        ["a network drop", 1006],
        ["a game end close whose game end it never got", 1000],
    ])("reports %s at once and resumes the seat after it", (_, code) => {
        let drops;
        ({ session, drops } = connectSession());
        latestSocket().receive(ROUND_STARTED);

        latestSocket().drop(code);
        expect(drops).toHaveLength(1);
        vi.advanceTimersByTime(1_000);
        latestSocket().open();

        expect(FakeWebSocket.created).toHaveLength(2);
        expect(latestSocket().sent).toEqual([RECONNECT]);
    });

    it("stays closed once the game has ended, reporting no drop", () => {
        let events, drops;
        ({ session, events, drops } = connectSession());

        latestSocket().receive({ t: 10, ws: 0, st: [], lb: 0 });
        latestSocket().drop();
        vi.advanceTimersByTime(60_000);

        expect(drops).toEqual([]);
        expect(events).toHaveLength(1);
        expect(FakeWebSocket.created).toHaveLength(1);
    });
});
