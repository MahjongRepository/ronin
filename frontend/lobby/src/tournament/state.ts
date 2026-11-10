import { type ChatEntry } from "@/chat";
import { type LobbySocket, type SocketStatus } from "@/lobby-socket";

type ConnectionStatus = SocketStatus | "connecting";

const PAGE_ERROR = {
    GAME_START_INVALID: "game_start_invalid",
    PAGE_SETUP_FAILED: "page_setup_failed",
} as const;

interface TournamentState {
    chatMessages: ChatEntry[];
    connectionStatus: ConnectionStatus;
    joined: boolean;
    pageError: string | null;
    players: string[];
    reconnectAttempts: number;
    reconnectTimer: ReturnType<typeof setTimeout> | null;
    reconnecting: boolean;
    socket: LobbySocket | null;
}

function createTournamentState(): TournamentState {
    return {
        chatMessages: [],
        connectionStatus: "connecting",
        joined: false,
        pageError: null,
        players: [],
        reconnectAttempts: 0,
        reconnectTimer: null,
        reconnecting: false,
        socket: null,
    };
}

function isOnline(state: TournamentState): boolean {
    return state.joined && state.pageError === null;
}

function isLive(state: TournamentState): boolean {
    return isOnline(state) && state.connectionStatus === "connected" && !state.reconnecting;
}

function isConnectionLost(state: TournamentState): boolean {
    const closed = state.connectionStatus === "disconnected" || state.connectionStatus === "error";
    return closed && state.pageError === null && state.reconnectTimer === null;
}

export { PAGE_ERROR, createTournamentState, isConnectionLost, isLive, isOnline };
export type { TournamentState };
