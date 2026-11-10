import { type CancelTimer, type Clock, browserClock } from "@/shared/clock";
import {
    CLOSE_CODE,
    type ClientMessage,
    SESSION_MESSAGE_TYPE,
    WIRE_KEY,
    buildPingMessage,
    decodeWireMessage,
    encodeWireMessage,
} from "@/shared/protocol";

/** What one socket reports; after `onClose` it reports nothing more. */
export interface SocketHandlers {
    readonly onOpen: () => void;
    readonly onMessage: (message: Record<string, unknown>) => void;
    readonly onClose: (code: number, reason: string) => void;
    /** The browser's socket error, which its close follows. */
    readonly onError: (detail: string) => void;
    /** A frame that decodes into no message: not binary, not MessagePack, or not an object. */
    readonly onUndecodableFrame: (detail: string) => void;
    /** The connection's round trip as the median of its latest pings, in milliseconds, after each pong. */
    readonly onRoundTrip: (roundTripMs: number) => void;
}

/** One connection attempt: it never reconnects by itself, and `disconnect` silences it. */
export interface GameConnection {
    readonly send: (message: ClientMessage) => void;
    readonly disconnect: () => void;
    /** How long a silent server is waited for before the silence is reported as a close, from the client's policy. */
    readonly setSilenceLimit: (limitMs: number) => void;
}

export type ConnectSocket = (url: string, handlers: SocketHandlers) => GameConnection;

/** The close the silence watchdog reports: what a browser reports for a connection lost without a close frame. */
const SERVER_SILENT_CLOSE = { code: CLOSE_CODE.ABNORMAL, reason: "server_silent" } as const;

/**
 * The silence a socket waits for until the client sets its limit from a wait the server names: the client's own bound
 * on the identity exchange, which the server answers at once, so it mirrors no server pacing.
 */
export const DEFAULT_SERVER_SILENCE_LIMIT_MS = 90_000;
const SILENCE_CHECK_INTERVAL_MS = 5000;
export const PING_INTERVAL_MS = 5000;
const ROUND_TRIP_SAMPLES = 5;
/** An unanswered ping this old is taken as lost (the server's rate limit drops a ping unanswered), and pinged anew. */
const LOST_PING_MS = 30_000;

type DecodedFrame =
    | { readonly ok: true; readonly message: Record<string, unknown> }
    | { readonly ok: false; readonly detail: string };

function isPong(message: Record<string, unknown>): boolean {
    return message[WIRE_KEY.SESSION_TYPE] === SESSION_MESSAGE_TYPE.PONG;
}

function median(samples: readonly number[]): number {
    const sorted = samples.toSorted((first, second) => first - second);
    return sorted[Math.floor((sorted.length - 1) / 2)];
}

function decodeFrame(data: unknown): DecodedFrame {
    if (!(data instanceof ArrayBuffer)) {
        return { detail: "Received a non-binary frame", ok: false };
    }
    try {
        return { message: decodeWireMessage(new Uint8Array(data)), ok: true };
    } catch {
        return { detail: "Failed to decode a MessagePack frame", ok: false };
    }
}

/**
 * The game server socket as an IO adapter: it decodes MessagePack frames and reports open, message, close and
 * error to its handlers, and decides nothing. A server silent longer than the limit the client sets (any legitimate
 * wait, by its policy) is reported as a close, measured on the steady clock, so the first check after a device wake
 * sees the whole gap and a wall clock set back hides no silence; a wall stepped forward (unless undoing a recent back
 * step) looks like a sleep, so a healthy socket is then reported silent and reconnected.
 *
 * It pings the server from its open on, one ping in flight at a time, and keeps the pongs to itself: each reports the
 * median of the latest round trips, so one late answer (a device waking) does not move it. A pong is no sign of the
 * game's life (the endpoint answers it without the session), so it never holds the silence watchdog off.
 */
export class GameSocket implements GameConnection {
    private readonly ws: WebSocket;
    private readonly handlers: SocketHandlers;
    private readonly clock: Clock;
    private silenceLimitMs = DEFAULT_SERVER_SILENCE_LIMIT_MS;
    private lastFrameAt = 0;
    private cancelWatchdog: CancelTimer | null = null;
    private cancelPing: CancelTimer | null = null;
    private pingSentAt: number | null = null;
    private roundTrips: readonly number[] = [];

    constructor(url: string, handlers: SocketHandlers, clock: Clock = browserClock) {
        this.handlers = handlers;
        this.clock = clock;
        this.ws = new WebSocket(url);
        this.ws.binaryType = "arraybuffer";
        this.listen();
    }

    send(message: ClientMessage): void {
        if (this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(encodeWireMessage(message));
        }
    }

    disconnect(): void {
        this.detach();
        this.ws.close();
    }

    setSilenceLimit(limitMs: number): void {
        this.silenceLimitMs = limitMs;
    }

    private listen(): void {
        this.ws.onopen = () => {
            this.lastFrameAt = this.clock.now();
            this.armWatchdog();
            this.ping();
            this.handlers.onOpen();
        };
        this.ws.onmessage = (event: MessageEvent) => this.receive(event.data);
        this.ws.onclose = (event: CloseEvent) => this.finish(event.code, event.reason);
        this.ws.onerror = () => this.handlers.onError("WebSocket error");
    }

    private receive(data: unknown): void {
        const frame = decodeFrame(data);
        if (frame.ok && isPong(frame.message)) {
            this.takePong();
            return;
        }
        this.lastFrameAt = this.clock.now();
        if (frame.ok) {
            this.handlers.onMessage(frame.message);
        } else {
            this.handlers.onUndecodableFrame(frame.detail);
        }
    }

    private ping(): void {
        const now = this.clock.now();
        if (this.pingSentAt === null || now - this.pingSentAt >= LOST_PING_MS) {
            this.pingSentAt = now;
            this.send(buildPingMessage());
        }
        this.cancelPing = this.clock.setTimer(PING_INTERVAL_MS, () => this.ping());
    }

    private takePong(): void {
        if (this.pingSentAt === null) {
            return;
        }
        const roundTrip = this.clock.now() - this.pingSentAt;
        this.pingSentAt = null;
        this.roundTrips = [...this.roundTrips, roundTrip].slice(-ROUND_TRIP_SAMPLES);
        this.handlers.onRoundTrip(median(this.roundTrips));
    }

    private armWatchdog(): void {
        this.cancelWatchdog = this.clock.setTimer(SILENCE_CHECK_INTERVAL_MS, () => {
            if (this.clock.now() - this.lastFrameAt <= this.silenceLimitMs) {
                this.armWatchdog();
                return;
            }
            this.ws.close();
            this.finish(SERVER_SILENT_CLOSE.code, SERVER_SILENT_CLOSE.reason);
        });
    }

    private finish(code: number, reason: string): void {
        this.detach();
        this.handlers.onClose(code, reason);
    }

    private detach(): void {
        this.cancelWatchdog?.();
        this.cancelWatchdog = null;
        this.cancelPing?.();
        this.cancelPing = null;
        this.ws.onopen = null;
        this.ws.onmessage = null;
        this.ws.onclose = null;
        this.ws.onerror = null;
    }
}
