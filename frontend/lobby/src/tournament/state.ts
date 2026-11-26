import { type ApiResult, isRecord } from "@/api";
import { type ChatEntry } from "@/chat";
import { type CurrentGame } from "@/current-games";
import { type MessageKey } from "@/i18n";
import { type LobbySocket, type SocketStatus } from "@/lobby-socket";
import { type LiveGameReturn, createLiveGameReturn } from "@/session";
import { type PlayedGame, readPlayedGames } from "@/tournament/played-games";

type ConnectionStatus = SocketStatus | "connecting";

const PAGE_ERROR = {
    GAME_START_INVALID: "game_start_invalid",
    PAGE_SETUP_FAILED: "page_setup_failed",
} as const;

const TOURNAMENT_NOT_FOUND = "tournament_not_found";

const TOURNAMENT_TABS = ["tournament", "settings"] as const;

type TournamentTab = (typeof TOURNAMENT_TABS)[number];

interface TournamentFinish {
    readonly finishedAt: Date;
    readonly played: readonly PlayedGame[];
}

interface TournamentConfig {
    readonly chatMaxLength: number;
    readonly finish: TournamentFinish | null;
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
    chatOpen: boolean;
    chatUnread: number;
    name: string | null;
    ownerBusy: boolean;
    ownerError: MessageKey | null;
    connectionStatus: ConnectionStatus;
    finishedAt: Date | null;
    games: CurrentGame[];
    joined: boolean;
    readonly liveGame: LiveGameReturn;
    pageError: string | null;
    played: readonly PlayedGame[];
    playedExpanded: boolean;
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
        chatOpen: false,
        chatUnread: 0,
        connectionStatus: "connecting",
        finishedAt: null,
        games: [],
        joined: false,
        liveGame: createLiveGameReturn(),
        name: null,
        ownerBusy: false,
        ownerError: null,
        pageError: null,
        played: [],
        playedExpanded: false,
        players: [],
        reconnectAttempts: 0,
        reconnectTimer: null,
        reconnecting: false,
        socket: null,
        tab: "tournament",
    };
}

function isFinished(state: TournamentState): boolean {
    return state.finishedAt !== null;
}

function isOnline(state: TournamentState): boolean {
    return state.joined && state.pageError === null && !isFinished(state);
}

function isLive(state: TournamentState): boolean {
    return isOnline(state) && state.connectionStatus === "connected" && !state.reconnecting;
}

function isConnectionLost(state: TournamentState): boolean {
    const closed = state.connectionStatus === "disconnected" || state.connectionStatus === "error";
    return (
        closed && state.pageError === null && !isFinished(state) && state.reconnectTimer === null
    );
}

function isPositiveInteger(value: unknown): value is number {
    return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isFilledString(value: unknown): value is string {
    return typeof value === "string" && value !== "";
}

function parseFinishedAt(data: unknown): Date | null {
    return isRecord(data) && typeof data.finished_at === "number"
        ? new Date(data.finished_at * 1000)
        : null;
}

function parseTournamentFinish(data: Record<string, unknown>): TournamentFinish | null {
    const finishedAt = parseFinishedAt(data);
    return finishedAt === null ? null : { finishedAt, played: readPlayedGames(data) };
}

function parseTournamentConfig(data: unknown): TournamentConfig | null {
    if (!isRecord(data)) {
        return null;
    }
    const {
        chat_max_length: chatMaxLength,
        finished_at: finishedAt,
        is_owner: isOwner,
        name,
        name_max_length: nameMaxLength,
        ws_url: wsUrl,
    } = data;
    if (
        !isFilledString(name) ||
        !isFilledString(wsUrl) ||
        typeof isOwner !== "boolean" ||
        (finishedAt !== null && typeof finishedAt !== "number") ||
        !isPositiveInteger(chatMaxLength) ||
        !isPositiveInteger(nameMaxLength)
    ) {
        return null;
    }
    return {
        chatMaxLength,
        finish: parseTournamentFinish(data),
        isOwner,
        name,
        nameMaxLength,
        wsUrl,
    };
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
    isFinished,
    isLive,
    isOnline,
    parseFinishedAt,
    parseRenamedName,
    readTournamentConfigAnswer,
};
export type {
    TournamentConfig,
    TournamentConfigAnswer,
    TournamentFinish,
    TournamentState,
    TournamentTab,
};
