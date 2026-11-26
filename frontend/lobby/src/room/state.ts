import { type ApiResult, isRecord } from "@/api";
import { type ChatEntry } from "@/chat";
import { formatList, t } from "@/i18n";
import { type LobbySocket, type SocketStatus } from "@/lobby-socket";

interface PlayerInfo {
    name: string;
    ready: boolean;
    is_bot: boolean;
    is_owner: boolean;
}

type ConnectionStatus = SocketStatus | "connecting";

interface PageError {
    code: string;
    seatedRoomId?: string;
}

interface RoomConfig {
    readonly chatMaxLength: number;
    readonly roomName: string;
    readonly wsUrl: string;
}

type RoomConfigAnswer =
    | { readonly kind: "open"; readonly config: RoomConfig }
    | { readonly kind: "gone"; readonly gameUrl: string | null }
    | { readonly kind: "failed" };

const ROOM_NOT_FOUND = "room_not_found";

const ROOM_SEATS = 4;

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
    handedOff: boolean;
    pageError: PageError | null;
    reconnectAttempts: number;
    reconnecting: boolean;
    socket: LobbySocket | null;
    strongBotSeats: number;
    strongBotsAvailable: boolean;
}

function createRoomState(): RoomState {
    return {
        canStart: false,
        chatMessages: [],
        connectionStatus: "connecting",
        currentPlayerName: "",
        handedOff: false,
        isOwner: false,
        joinRetries: 0,
        joinRetryTimer: null,
        pageError: null,
        players: [],
        reconnectAttempts: 0,
        reconnecting: false,
        socket: null,
        strongBotSeats: 0,
        strongBotsAvailable: false,
    };
}

function resetSeat(state: RoomState): void {
    const { socket } = state;
    Object.assign(state, createRoomState(), { socket });
}

function hasEnded(state: RoomState): boolean {
    return state.pageError !== null || state.handedOff;
}

function isSeated(state: RoomState): boolean {
    return state.currentPlayerName !== "" && !hasEnded(state);
}

function isMe(state: RoomState, player: PlayerInfo): boolean {
    return !player.is_bot && player.name === state.currentPlayerName;
}

function canAct(state: RoomState): boolean {
    return isSeated(state) && state.connectionStatus === "connected" && !state.reconnecting;
}

function isConnectionLost(state: RoomState): boolean {
    const closed = state.connectionStatus === "disconnected" || state.connectionStatus === "error";
    return closed && state.pageError === null && state.joinRetryTimer === null;
}

function getMyReadyState(state: RoomState): boolean {
    return state.players.find((player) => isMe(state, player))?.ready ?? false;
}

function countOpenSeats(state: RoomState): number {
    return state.players.filter((player) => player.is_bot).length;
}

function offersStrongBots(state: RoomState): boolean {
    return (
        state.isOwner && isSeated(state) && (state.strongBotsAvailable || state.strongBotSeats > 0)
    );
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
    return t("room.waiting_for", { names: formatList(waitingFor) });
}

function parseRoomConfig(data: unknown): RoomConfig | null {
    if (!isRecord(data)) {
        return null;
    }
    const { chat_max_length: chatMaxLength, room_name: roomName, ws_url: wsUrl } = data;
    if (
        typeof roomName !== "string" ||
        roomName === "" ||
        typeof wsUrl !== "string" ||
        wsUrl === "" ||
        typeof chatMaxLength !== "number" ||
        !Number.isInteger(chatMaxLength) ||
        chatMaxLength <= 0
    ) {
        return null;
    }
    return { chatMaxLength, roomName, wsUrl };
}

function readGameUrl(data: unknown): string | null {
    return isRecord(data) && typeof data.game_url === "string" && data.game_url !== ""
        ? data.game_url
        : null;
}

function readRoomConfigAnswer(result: ApiResult): RoomConfigAnswer {
    if (!result.ok) {
        return result.error === ROOM_NOT_FOUND
            ? { gameUrl: readGameUrl(result.data), kind: "gone" }
            : { kind: "failed" };
    }
    const config = parseRoomConfig(result.data);
    return config === null ? { kind: "failed" } : { config, kind: "open" };
}

export {
    PAGE_ERROR,
    ROOM_SEATS,
    canAct,
    countOpenSeats,
    createRoomState,
    describeStartBlocker,
    getMyReadyState,
    hasEnded,
    isConnectionLost,
    isMe,
    isSeated,
    offersStrongBots,
    readRoomConfigAnswer,
    resetSeat,
};
export type { ConnectionStatus, PageError, PlayerInfo, RoomConfig, RoomConfigAnswer, RoomState };
