import { type CurrentGame, readCurrentGames } from "@/current-games";
import { LobbySocket, type SocketStatus } from "@/lobby-socket";
import { bindToPageLifetime, bindToResume } from "@/page-lifetime";

const GAMES_MESSAGE = "games";
const RECONNECT_FIRST_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 15_000;
const MAX_RECONNECT_ATTEMPTS = 24;
const RESUME_RECONNECT_AFTER_HIDDEN_MS = 20_000;

export type ShowGames = (games: CurrentGame[]) => void;

class CurrentGamesFeed {
    private attempts = 0;
    private released = false;
    private timer: ReturnType<typeof setTimeout> | null = null;
    private readonly socket: LobbySocket;
    private readonly url: string;

    constructor(url: string, show: ShowGames) {
        this.url = url;
        this.socket = new LobbySocket(
            (message) => {
                if (message.type === GAMES_MESSAGE) {
                    show(readCurrentGames(message));
                }
            },
            (status) => this.onStatus(status),
        );
    }

    connect(): void {
        this.cancelReconnect();
        this.released = false;
        this.socket.connect(this.url);
    }

    release(): void {
        this.released = true;
        this.cancelReconnect();
        this.socket.disconnect();
    }

    reconnectOnResume(): void {
        if (!this.released) {
            this.attempts = 0;
            this.connect();
        }
    }

    private onStatus(status: SocketStatus): void {
        if (status === "connected") {
            this.attempts = 0;
            return;
        }
        this.scheduleReconnect();
    }

    private scheduleReconnect(): void {
        if (this.released || this.timer !== null || this.attempts >= MAX_RECONNECT_ATTEMPTS) {
            return;
        }
        const delay = Math.min(
            RECONNECT_FIRST_DELAY_MS * 2 ** this.attempts,
            RECONNECT_MAX_DELAY_MS,
        );
        this.attempts += 1;
        this.timer = setTimeout(() => {
            this.timer = null;
            this.socket.connect(this.url);
        }, delay);
    }

    private cancelReconnect(): void {
        if (this.timer !== null) {
            clearTimeout(this.timer);
            this.timer = null;
        }
    }
}

export function watchCurrentGames(url: string, show: ShowGames): () => void {
    const feed = new CurrentGamesFeed(url, show);
    const unbindLifetime = bindToPageLifetime({
        release: () => feed.release(),
        restore: () => feed.connect(),
    });
    const unbindResume = bindToResume(
        () => feed.reconnectOnResume(),
        RESUME_RECONNECT_AFTER_HIDDEN_MS,
    );
    feed.connect();
    return () => {
        feed.release();
        unbindLifetime();
        unbindResume();
    };
}
