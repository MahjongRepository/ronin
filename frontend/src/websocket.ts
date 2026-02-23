import { ClientMessageType, ConnectionStatus, InternalMessageType } from "./protocol";
import { decode, encode } from "@msgpack/msgpack";

export type MessageHandler = (message: Record<string, unknown>) => void;
export type StatusHandler = (status: ConnectionStatus) => void;

const MAX_RECONNECT_ATTEMPTS = 10;
const MAX_BACKOFF_MS = 30_000;

export class GameSocket {
    private ws: WebSocket | null = null;
    private pingInterval: ReturnType<typeof setInterval> | null = null;
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
        this.onStatusChange(ConnectionStatus.CONNECTING);
        const ws = new WebSocket(websocketUrl);
        this.ws = ws;
        ws.binaryType = "arraybuffer";

        ws.onopen = () => {
            if (this.ws !== ws) {
                return;
            }
            this.reconnectAttempts = 0;
            this.onStatusChange(ConnectionStatus.CONNECTED);
            this.pingInterval = setInterval(() => {
                this.send({ t: ClientMessageType.PING });
            }, 10_000);
        };

        ws.onmessage = (event: MessageEvent) => {
            if (this.ws !== ws) {
                return;
            }
            const { data } = event;
            if (data instanceof ArrayBuffer) {
                try {
                    const message = decode(new Uint8Array(data)) as Record<string, unknown>;
                    this.onMessage(message);
                } catch {
                    this.onMessage({
                        error: "failed to decode MessagePack frame",
                        type: InternalMessageType.DECODE_ERROR,
                    });
                }
            }
        };

        ws.onclose = () => {
            if (this.ws !== ws) {
                return;
            }
            this.clearPingInterval();
            this.ws = null;
            this.onStatusChange(ConnectionStatus.DISCONNECTED);
            this.scheduleReconnect();
        };

        ws.onerror = () => {
            if (this.ws !== ws) {
                return;
            }
            this.onStatusChange(ConnectionStatus.ERROR);
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
        this.clearPingInterval();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
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

    private clearPingInterval(): void {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    // detach handlers before closing to prevent stale onclose from
    // nullifying the reference to a new socket created below
    private disconnectExisting(): void {
        this.clearPingInterval();
        if (!this.ws) {
            return;
        }
        this.ws.onopen = null;
        this.ws.onmessage = null;
        this.ws.onclose = null;
        this.ws.onerror = null;
        this.ws.close();
        this.ws = null;
    }
}
