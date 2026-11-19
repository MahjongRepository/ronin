import { type ApiResult, isRecord } from "@/api";
import { type ChatEntry } from "@/chat";
import { type CurrentGame } from "@/current-games";
import { type MessageKey } from "@/i18n";
import { type LobbySocket, type SocketStatus } from "@/lobby-socket";

type ConnectionStatus = SocketStatus | "connecting";

const PAGE_ERROR = {
    GAME_START_INVALID: "game_start_invalid",
    PAGE_SETUP_FAILED: "page_setup_failed",
} as const;

const TOURNAMENT_NOT_FOUND = "tournament_not_found";

const TOURNAMENT_TABS = ["tournament", "settings"] as const;

type TournamentTab = (typeof TOURNAMENT_TABS)[number];

interface TournamentConfig {
    readonly chatMaxLength: number;
    readonly isOwner: boolean;
    readonly name: string;
    readonly nameMaxLength: number;
    readonly wsUrl: string;
}

type TournamentConfigAnswer =
    | { readonly kind: "open"; readonly config: TournamentConfig }
    | { readonly kind: "gone" }
    | { readonly kind: "failed" };

interface TournamentState {
    chatMessages: ChatEntry[];
    name: string | null;
    ownerBusy: boolean;
    ownerError: MessageKey | null;
    connectionStatus: ConnectionStatus;
    games: CurrentGame[];
    joined: boolean;
    pageError: string | null;
    players: string[];
    reconnectAttempts: number;
    reconnectTimer: ReturnType<typeof setTimeout> | null;
    reconnecting: boolean;
    socket: LobbySocket | null;
    tab: TournamentTab;
}

function createTournamentState(): TournamentState {
    return {
        chatMessages: [],
        connectionStatus: "connecting",
        games: [],
        joined: false,
        name: null,
        ownerBusy: false,
        ownerError: null,
        pageError: null,
        players: [],
        reconnectAttempts: 0,
        reconnectTimer: null,
        reconnecting: false,
        socket: null,
        tab: "tournament",
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

function isPositiveInteger(value: unknown): value is number {
    return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isFilledString(value: unknown): value is string {
    return typeof value === "string" && value !== "";
}

function parseTournamentConfig(data: unknown): TournamentConfig | null {
    if (!isRecord(data)) {
        return null;
    }
    const {
        chat_max_length: chatMaxLength,
        is_owner: isOwner,
        name,
        name_max_length: nameMaxLength,
        ws_url: wsUrl,
    } = data;
    if (
        !isFilledString(name) ||
        !isFilledString(wsUrl) ||
        typeof isOwner !== "boolean" ||
        !isPositiveInteger(chatMaxLength) ||
        !isPositiveInteger(nameMaxLength)
    ) {
        return null;
    }
    return { chatMaxLength, isOwner, name, nameMaxLength, wsUrl };
}

function readTournamentConfigAnswer(result: ApiResult): TournamentConfigAnswer {
    if (!result.ok) {
        return result.error === TOURNAMENT_NOT_FOUND ? { kind: "gone" } : { kind: "failed" };
    }
    const config = parseTournamentConfig(result.data);
    return config === null ? { kind: "failed" } : { config, kind: "open" };
}

function parseRenamedName(data: unknown): string | null {
    return isRecord(data) && isFilledString(data.name) ? data.name : null;
}

export {
    PAGE_ERROR,
    TOURNAMENT_NOT_FOUND,
    TOURNAMENT_TABS,
    createTournamentState,
    isConnectionLost,
    isLive,
    isOnline,
    parseRenamedName,
    readTournamentConfigAnswer,
};
export type { TournamentConfig, TournamentConfigAnswer, TournamentState, TournamentTab };
