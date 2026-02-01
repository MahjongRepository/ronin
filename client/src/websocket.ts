import { decode, encode } from "@msgpack/msgpack";

type MessageHandler = (message: Record<string, unknown>) => void;

export class GameSocket {
    private ws: WebSocket | null = null;
    private onMessage: MessageHandler;
    private onStatusChange: (status: string) => void;

    constructor(onMessage: MessageHandler, onStatusChange: (status: string) => void) {
        this.onMessage = onMessage;
        this.onStatusChange = onStatusChange;
    }

    connect(websocketUrl: string): void {
        this.disconnectExisting();
        this.onStatusChange("connecting");
        const ws = new WebSocket(websocketUrl);
        this.ws = ws;
        ws.binaryType = "arraybuffer";

        ws.onopen = () => {
            if (this.ws !== ws) {
                return;
            }
            this.onStatusChange("connected");
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
                        type: "decode_error",
                    });
                }
            }
        };

        ws.onclose = () => {
            if (this.ws !== ws) {
                return;
            }
            this.onStatusChange("disconnected");
            this.ws = null;
        };

        ws.onerror = () => {
            if (this.ws !== ws) {
                return;
            }
            this.onStatusChange("error");
        };
    }

    send(message: Record<string, unknown>): void {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(encode(message));
        }
    }

    disconnect(): void {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    // detach handlers before closing to prevent stale onclose from
    // nullifying the reference to a new socket created below
    private disconnectExisting(): void {
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
