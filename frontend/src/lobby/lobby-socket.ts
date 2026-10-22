export type MessageHandler = (message: Record<string, unknown>) => void;
export type StatusHandler = (status: "connected" | "disconnected" | "error") => void;

export class LobbySocket {
    private ws: WebSocket | null = null;
    private onMessage: MessageHandler;
    private onStatusChange: StatusHandler;

    constructor(onMessage: MessageHandler, onStatusChange: StatusHandler) {
        this.onMessage = onMessage;
        this.onStatusChange = onStatusChange;
    }

    connect(url: string): void {
        this.disconnectExisting();
        const ws = new WebSocket(url);
        this.ws = ws;

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
            if (typeof event.data === "string") {
                try {
                    const message = JSON.parse(event.data) as Record<string, unknown>;
                    this.onMessage(message);
                } catch {
                    this.onMessage({ message: "Failed to parse server message", type: "error" });
                }
            }
        };

        ws.onclose = () => {
            if (this.ws !== ws) {
                return;
            }
            this.ws = null;
            this.onStatusChange("disconnected");
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
            this.ws.send(JSON.stringify(message));
        }
    }

    disconnect(): void {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

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
