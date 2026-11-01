import { decode, encode } from "@msgpack/msgpack";

import { type CancelTimer, type Clock, browserClock } from "@/shared/clock";
import { CLOSE_CODE, type ClientMessage } from "@/shared/protocol";

/** What one socket reports; after `onClose` it reports nothing more. */
export interface SocketHandlers {
    readonly onOpen: () => void;
    readonly onMessage: (message: Record<string, unknown>) => void;
    readonly onClose: (code: number, reason: string) => void;
    /** The browser's socket error, which its close follows. */
    readonly onError: (detail: string) => void;
    /** A frame that decodes into no message: not binary, not MessagePack, or not an object. */
    readonly onUndecodableFrame: (detail: string) => void;
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

function isWireRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

type DecodedFrame =
    | { readonly ok: true; readonly message: Record<string, unknown> }
    | { readonly ok: false; readonly detail: string };

function decodeFrame(data: unknown): DecodedFrame {
    if (!(data instanceof ArrayBuffer)) {
        return { detail: "Received a non-binary frame", ok: false };
    }
    let message: unknown = null;
    try {
        message = decode(new Uint8Array(data));
    } catch {
        return { detail: "Failed to decode a MessagePack frame", ok: false };
    }
    return isWireRecord(message)
        ? { message, ok: true }
        : { detail: "Received a frame that is not a message object", ok: false };
}

/**
 * The game server socket as an IO adapter: it decodes MessagePack frames and reports open, message, close and
 * error to its handlers, and decides nothing. A server silent longer than the limit the client sets (any legitimate
 * wait, by its policy) is reported as a close, measured on the steady clock, so the first check after a device wake
 * sees the whole gap and a wall clock set back hides no silence; a wall stepped forward (unless undoing a recent back
 * step) looks like a sleep, so a healthy socket is then reported silent and reconnected.
 */
export class GameSocket implements GameConnection {
    private readonly ws: WebSocket;
    private readonly handlers: SocketHandlers;
    private readonly clock: Clock;
    private silenceLimitMs = DEFAULT_SERVER_SILENCE_LIMIT_MS;
    private lastFrameAt = 0;
    private cancelWatchdog: CancelTimer | null = null;

    constructor(url: string, handlers: SocketHandlers, clock: Clock = browserClock) {
        this.handlers = handlers;
        this.clock = clock;
        this.ws = new WebSocket(url);
        this.ws.binaryType = "arraybuffer";
        this.listen();
    }

    send(message: ClientMessage): void {
        if (this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(encode(message));
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
            this.handlers.onOpen();
        };
        this.ws.onmessage = (event: MessageEvent) => this.receive(event.data);
        this.ws.onclose = (event: CloseEvent) => this.finish(event.code, event.reason);
        this.ws.onerror = () => this.handlers.onError("WebSocket error");
    }

    private receive(data: unknown): void {
        this.lastFrameAt = this.clock.now();
        const frame = decodeFrame(data);
        if (frame.ok) {
            this.handlers.onMessage(frame.message);
        } else {
            this.handlers.onUndecodableFrame(frame.detail);
        }
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
        this.ws.onopen = null;
        this.ws.onmessage = null;
        this.ws.onclose = null;
        this.ws.onerror = null;
    }
}
