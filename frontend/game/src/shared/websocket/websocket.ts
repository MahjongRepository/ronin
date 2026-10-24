import { decode, encode } from "@msgpack/msgpack";

import { CONNECTION_STATUS, type ConnectionStatus, INTERNAL_MESSAGE_TYPE } from "@/shared/protocol";

export type MessageHandler = (message: Record<string, unknown>) => void;
export type StatusHandler = (status: ConnectionStatus) => void;

const MAX_RECONNECT_ATTEMPTS = 10;
const MAX_BACKOFF_MS = 30_000;
const SERVER_SILENCE_LIMIT_MS = 90_000;
const SILENCE_CHECK_INTERVAL_MS = 5000;

export class GameSocket {
    private ws: WebSocket | null = null;
    private lastFrameAt = 0;
    private silenceWatchdog: ReturnType<typeof setInterval> | null = null;
    private onMessage: MessageHandler;
    private onStatusChange: StatusHandler;

    private reconnectAttempts = 0;
    private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    private reconnectEnabled = false;
    private reconnectUrl: string | null = null;
    private onReconnect: (() => void) | null = null;

    constructor(onMessage: MessageHandler, onStatusChange: StatusHandler) {
        this.onMessage = onMessage;
        this.onStatusChange = onStatusChange;
    }

    connect(websocketUrl: string): void {
        this.disconnectExisting();
        this.onStatusChange(CONNECTION_STATUS.CONNECTING);
        const ws = new WebSocket(websocketUrl);
        this.ws = ws;
        ws.binaryType = "arraybuffer";

        ws.onopen = () => {
            if (this.ws !== ws) {
                return;
            }
            this.reconnectAttempts = 0;
            this.startSilenceWatchdog(ws);
            this.onStatusChange(CONNECTION_STATUS.CONNECTED);
        };

        ws.onmessage = (event: MessageEvent) => {
            if (this.ws !== ws) {
                return;
            }
            this.lastFrameAt = Date.now();
            const { data } = event;
            if (data instanceof ArrayBuffer) {
                try {
                    const message = decode(new Uint8Array(data)) as Record<string, unknown>;
                    this.onMessage(message);
                } catch {
                    this.onMessage({
                        error: "failed to decode MessagePack frame",
                        type: INTERNAL_MESSAGE_TYPE.DECODE_ERROR,
                    });
                }
            }
        };

        ws.onclose = () => {
            if (this.ws !== ws) {
                return;
            }
            this.handleClosed();
        };

        ws.onerror = () => {
            if (this.ws !== ws) {
                return;
            }
            this.onStatusChange(CONNECTION_STATUS.ERROR);
        };
    }

    /** Enable auto-reconnect on disconnect with exponential backoff. */
    enableReconnect(url: string, onReconnect?: () => void): void {
        this.reconnectEnabled = true;
        this.reconnectUrl = url;
        this.onReconnect = onReconnect ?? null;
    }

    /** Disable auto-reconnect and cancel any pending retry. */
    disableReconnect(): void {
        this.reconnectEnabled = false;
        this.reconnectUrl = null;
        this.onReconnect = null;
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }

    /** Whether the underlying WebSocket is currently open. */
    get isOpen(): boolean {
        return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
    }

    send(message: Record<string, unknown>): void {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(encode(message));
        }
    }

    disconnect(): void {
        this.disableReconnect();
        this.stopSilenceWatchdog();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    private handleClosed(): void {
        this.stopSilenceWatchdog();
        this.ws = null;
        this.onStatusChange(CONNECTION_STATUS.DISCONNECTED);
        this.scheduleReconnect();
    }

    private startSilenceWatchdog(ws: WebSocket): void {
        this.stopSilenceWatchdog();
        this.lastFrameAt = Date.now();
        this.silenceWatchdog = setInterval(() => {
            if (this.ws === ws && Date.now() - this.lastFrameAt > SERVER_SILENCE_LIMIT_MS) {
                this.detachHandlers(ws);
                ws.close();
                this.handleClosed();
            }
        }, SILENCE_CHECK_INTERVAL_MS);
    }

    private stopSilenceWatchdog(): void {
        if (this.silenceWatchdog) {
            clearInterval(this.silenceWatchdog);
            this.silenceWatchdog = null;
        }
    }

    private detachHandlers(ws: WebSocket): void {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onclose = null;
        ws.onerror = null;
    }

    private scheduleReconnect(): void {
        if (!this.reconnectEnabled || !this.reconnectUrl) {
            return;
        }
        if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            return;
        }

        const delayMs = Math.min(1000 * 2 ** this.reconnectAttempts, MAX_BACKOFF_MS);
        this.reconnectAttempts++;

        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.executeReconnect();
        }, delayMs);
    }

    private executeReconnect(): void {
        if (!this.reconnectEnabled || !this.reconnectUrl) {
            return;
        }
        const savedCallback = this.onReconnect;

        this.connect(this.reconnectUrl);
        this.wrapOnopenForReconnect(savedCallback);
    }

    private wrapOnopenForReconnect(callback: (() => void) | null): void {
        const { ws } = this;
        if (!ws) {
            return;
        }
        const originalOnopen = ws.onopen;
        ws.onopen = (event) => {
            if (originalOnopen) {
                (originalOnopen as (ev: Event) => void)(event);
            }
            if (callback && this.ws === ws) {
                callback();
            }
        };
    }

    // detach handlers before closing to prevent stale onclose from
    // nullifying the reference to a new socket created below
    private disconnectExisting(): void {
        this.stopSilenceWatchdog();
        if (!this.ws) {
            return;
        }
        this.detachHandlers(this.ws);
        this.ws.close();
        this.ws = null;
    }
}
