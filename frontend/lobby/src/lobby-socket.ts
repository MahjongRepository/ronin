export type SocketStatus = "connected" | "disconnected" | "error";

const LEAVING_CLOSE_CODE = 1000;
const REPLACING_CLOSE_CODE = 4100;
export type MessageHandler = (message: Record<string, unknown>) => void;
export type StatusHandler = (status: SocketStatus) => void;

export function readString(message: Record<string, unknown>, key: string): string | null {
    const value = message[key];
    return typeof value === "string" && value !== "" ? value : null;
}

export class LobbySocket {
    private ws: WebSocket | null = null;
    private onMessage: MessageHandler;
    private onStatusChange: StatusHandler;

    constructor(onMessage: MessageHandler, onStatusChange: StatusHandler) {
        this.onMessage = onMessage;
        this.onStatusChange = onStatusChange;
    }

    connect(url: string): void {
        this.dropSocket(REPLACING_CLOSE_CODE);
        const ws = new WebSocket(url);
        this.ws = ws;
        let failed = false;

        ws.addEventListener("open", () => {
            if (this.ws !== ws) {
                return;
            }
            this.onStatusChange("connected");
        });

        ws.addEventListener("message", (event) => {
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
        });

        ws.addEventListener("close", () => {
            if (this.ws !== ws) {
                return;
            }
            this.ws = null;
            if (!failed) {
                this.onStatusChange("disconnected");
            }
        });

        ws.addEventListener("error", () => {
            if (this.ws !== ws) {
                return;
            }
            failed = true;
            this.onStatusChange("error");
        });
    }

    send(message: Record<string, unknown>): boolean {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return false;
        }
        this.ws.send(JSON.stringify(message));
        return true;
    }

    disconnect(): void {
        this.dropSocket(LEAVING_CLOSE_CODE);
    }

    private dropSocket(code: number): void {
        if (this.ws) {
            this.ws.close(code);
            this.ws = null;
        }
    }
}
