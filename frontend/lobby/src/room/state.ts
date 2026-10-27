import { type LobbySocket, type SocketStatus } from "@/lobby-socket";

interface PlayerInfo {
    name: string;
    ready: boolean;
    is_bot: boolean;
    is_owner: boolean;
}

interface ChatEntry {
    sender: string;
    text: string;
    timestamp: string;
}

type ConnectionStatus = SocketStatus | "connecting";

interface PageError {
    code: string;
    seatedRoomId?: string;
    text: string;
}

const LOG_TYPE_SYSTEM = "system";

const PAGE_ERROR = {
    GAME_START_INVALID: "game_start_invalid",
    JOIN_RETRIES_EXHAUSTED: "join_retries_exhausted",
    PAGE_SETUP_FAILED: "page_setup_failed",
} as const;

interface RoomState {
    players: PlayerInfo[];
    chatMessages: ChatEntry[];
    connectionStatus: ConnectionStatus;
    isOwner: boolean;
    canStart: boolean;
    currentPlayerName: string;
    joinRetries: number;
    joinRetryTimer: ReturnType<typeof setTimeout> | null;
    pageError: PageError | null;
    socket: LobbySocket | null;
}

function createRoomState(): RoomState {
    return {
        canStart: false,
        chatMessages: [],
        connectionStatus: "connecting",
        currentPlayerName: "",
        isOwner: false,
        joinRetries: 0,
        joinRetryTimer: null,
        pageError: null,
        players: [],
        socket: null,
    };
}

function resetSeat(state: RoomState): void {
    const { socket } = state;
    Object.assign(state, createRoomState(), { socket });
}

function isSeated(state: RoomState): boolean {
    return state.currentPlayerName !== "" && state.pageError === null;
}

function isMe(state: RoomState, player: PlayerInfo): boolean {
    return !player.is_bot && player.name === state.currentPlayerName;
}

function canAct(state: RoomState): boolean {
    return isSeated(state) && state.connectionStatus === "connected";
}

function isConnectionLost(state: RoomState): boolean {
    const closed = state.connectionStatus === "disconnected" || state.connectionStatus === "error";
    return closed && state.pageError === null && state.joinRetryTimer === null;
}

function getMyReadyState(state: RoomState): boolean {
    return state.players.find((player) => isMe(state, player))?.ready ?? false;
}

function joinNames(names: readonly string[]): string {
    if (names.length <= 1) {
        return names.join("");
    }
    return `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}

function describeStartBlocker(state: RoomState): string | null {
    if (state.canStart) {
        return null;
    }
    const waitingFor = state.players
        .filter((player) => !player.is_bot && !player.is_owner && !player.ready)
        .map((player) => player.name);
    if (waitingFor.length === 0) {
        return null;
    }
    return `Waiting for ${joinNames(waitingFor)} to get ready.`;
}

export {
    LOG_TYPE_SYSTEM,
    PAGE_ERROR,
    canAct,
    createRoomState,
    describeStartBlocker,
    getMyReadyState,
    isConnectionLost,
    isMe,
    isSeated,
    resetSeat,
};
export type { ChatEntry, ConnectionStatus, PageError, PlayerInfo, RoomState };
