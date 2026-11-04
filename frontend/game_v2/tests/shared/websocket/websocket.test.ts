import { encode } from "@msgpack/msgpack";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ManualClock, steadyClockOn } from "#tests/fixtures/clock";
import { type Clock } from "@/shared/clock";
import {
    CLIENT_MESSAGE_TYPE,
    WIRE_KEY,
    buildJoinGameMessage,
    decodeWireMessage,
    encodeWireMessage,
} from "@/shared/protocol";
import { GameSocket, type SocketHandlers } from "@/shared/websocket/websocket";

class FakeWebSocket {
    static readonly OPEN = 1;
    static created: FakeWebSocket[] = [];

    binaryType = "blob";
    readyState = 0;
    closed = false;
    sent: Uint8Array[] = [];
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

    send(data: Uint8Array): void {
        this.sent.push(data);
    }

    close(): void {
        this.closed = true;
    }
}

let socket: GameSocket | null = null;

function connectedSocket(
    closes: [number, string][],
    handlers: Partial<SocketHandlers> = {},
    clock: Clock = steadyClockOn(new ManualClock()),
): FakeWebSocket {
    socket = new GameSocket(
        "ws://game/ws/g1",
        {
            onClose: (code, reason) => closes.push([code, reason]),
            onError: () => {},
            onMessage: () => {},
            onOpen: () => {},
            onUndecodableFrame: () => {},
            ...handlers,
        },
        clock,
    );
    const [ws] = FakeWebSocket.created;
    ws.open();
    return ws;
}

/** A socket on a hand-moved clock, open at time 0. */
function socketOnClock(): {
    closes: [number, string][];
    clock: ManualClock;
    ws: FakeWebSocket;
} {
    const clock = new ManualClock();
    const closes: [number, string][] = [];
    const ws = connectedSocket(closes, {}, steadyClockOn(clock));
    return { clock, closes, ws };
}

const HOUR_MS = 3_600_000;

describe("GameSocket silence watchdog", () => {
    beforeEach(() => {
        FakeWebSocket.created = [];
        vi.stubGlobal("WebSocket", FakeWebSocket);
    });

    afterEach(() => {
        socket?.disconnect();
        socket = null;
        vi.unstubAllGlobals();
    });

    it("keeps a socket that hears from the server within the limit, reports a longer silence as a close, and never reconnects itself", () => {
        const { clock, closes, ws } = socketOnClock();

        clock.advanceTo(60_000);
        ws.receiveFrame();
        clock.advanceTo(145_000);
        expect([ws.closed, closes]).toEqual([false, []]);

        clock.advanceTo(155_000);
        expect([ws.closed, closes]).toEqual([true, [[1006, "server_silent"]]]);

        clock.advanceTo(275_000);
        expect([FakeWebSocket.created.length, closes.length]).toEqual([1, 1]);
    });

    it("waits out the silence limit the client sets, so a longer time control's turn is never taken for a lost connection", () => {
        const { clock, closes, ws } = socketOnClock();
        socket?.setSilenceLimit(150_000);

        clock.advanceTo(145_000);
        expect([ws.closed, closes]).toEqual([false, []]);

        clock.advanceTo(155_000);
        expect([ws.closed, closes]).toEqual([true, [[1006, "server_silent"]]]);
    });

    it.each([
        ["elapsed time ran through it", (clock: ManualClock) => clock.advanceTo(120_000)],
        [
            "elapsed time paused, as a forward wall step looks",
            (clock: ManualClock) => clock.stepWall(120_000),
        ],
    ])(
        "reports the close on the first check after the device wakes from a long sleep (%s)",
        (_sleep, sleep) => {
            const { clock, closes, ws } = socketOnClock();

            sleep(clock);
            clock.advanceTo(clock.elapsedNow() + 5000);
            expect([ws.closed, closes]).toEqual([true, [[1006, "server_silent"]]]);
        },
    );

    it("reports a silence past the limit even after the wall clock stepped back an hour", () => {
        const { clock, closes, ws } = socketOnClock();
        clock.stepWall(-HOUR_MS);

        clock.advanceTo(90_000);
        expect([ws.closed, closes]).toEqual([false, []]);

        clock.advanceTo(95_000);
        expect([ws.closed, closes]).toEqual([true, [[1006, "server_silent"]]]);
    });

    it("keeps a socket that hears from the server when the wall clock steps back an hour and is set right again", () => {
        const { clock, closes, ws } = socketOnClock();
        clock.stepWall(-HOUR_MS);
        clock.advanceTo(5000);
        ws.receiveFrame();

        clock.stepWall(HOUR_MS);
        clock.advanceTo(10_000);
        expect([ws.closed, closes]).toEqual([false, []]);
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
        ws.receiveFrame(new Uint8Array(encode({ [WIRE_KEY.EVENT_TYPE]: 1 })).buffer);
        ws.receiveFrame(encodeWireMessage({ [WIRE_KEY.EVENT_TYPE]: 1 }).buffer);
        ws.fail();
        expect(reports).toEqual([
            "undecodable: Received a non-binary frame",
            "undecodable: Failed to decode a MessagePack frame",
            "undecodable: Failed to decode a MessagePack frame",
            "undecodable: Failed to decode a MessagePack frame",
            `message: ${JSON.stringify({ [WIRE_KEY.EVENT_TYPE]: 1 })}`,
            "error: WebSocket error",
        ]);
    });

    it("sends named client fields as integer map keys and reports readable incoming fields", () => {
        const messages: Record<string, unknown>[] = [];
        const ws = connectedSocket([], { onMessage: (message) => messages.push(message) });
        socket?.send(buildJoinGameMessage("ticket"));
        expect(ws.sent).toHaveLength(1);
        expect(ws.sent[0]).toEqual(
            new Uint8Array([
                0x82,
                WIRE_KEY.EVENT_TYPE,
                CLIENT_MESSAGE_TYPE.JOIN_GAME,
                WIRE_KEY.GAME_TICKET,
                ...encode("ticket"),
            ]),
        );
        expect(decodeWireMessage(ws.sent[0])).toEqual(buildJoinGameMessage("ticket"));
        ws.receiveFrame(
            encodeWireMessage({ [WIRE_KEY.PACKED_MOVE]: 37, [WIRE_KEY.EVENT_TYPE]: 2 }).buffer,
        );
        expect(messages).toEqual([{ [WIRE_KEY.PACKED_MOVE]: 37, [WIRE_KEY.EVENT_TYPE]: 2 }]);
    });
});
