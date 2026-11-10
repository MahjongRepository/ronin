import { LOG_TYPE_SYSTEM } from "@/chat";
import { type MessageKey, formatList, formatTime, reportI18nError, t } from "@/i18n";
import { type SocketStatus, readString } from "@/lobby-socket";
import { OCCUPANCY } from "@/occupancy-errors";
import { enterGame, readGameStart } from "@/session";
import {
    PAGE_ERROR,
    type TournamentState,
    createTournamentState,
    isLive,
    isOnline,
} from "@/tournament/state";

type RenderTournament = () => void;

type MessageHandlerMap = Record<string, (msg: Record<string, unknown>) => void>;

const RECONNECT_FIRST_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 15_000;
const MAX_RECONNECT_ATTEMPTS = 24;
const RESUME_RECONNECT_AFTER_HIDDEN_MS = 20_000;

const TOURNAMENT_DELETED = "tournament_deleted";

const TOURNAMENT_ERROR_CODES = [
    "rate_limited",
    "tournament_not_found",
    TOURNAMENT_DELETED,
    OCCUPANCY.REPLACED_BY_NEW_CONNECTION,
    PAGE_ERROR.GAME_START_INVALID,
    PAGE_ERROR.PAGE_SETUP_FAILED,
] as const;

type TournamentErrorCode = (typeof TOURNAMENT_ERROR_CODES)[number];

function isTournamentErrorCode(code: unknown): code is TournamentErrorCode {
    return TOURNAMENT_ERROR_CODES.some((known) => known === code);
}

function tournamentErrorKey(code: TournamentErrorCode): MessageKey {
    return `tournament.error.${code}`;
}

function describeTournamentError(code: unknown): string {
    if (isTournamentErrorCode(code)) {
        return t(tournamentErrorKey(code));
    }
    reportI18nError(`tournament.error.${String(code)}`, "unknown tournament error code");
    return t("tournament.error.unknown");
}

function readNames(message: Record<string, unknown>): string[] | null {
    const { players } = message;
    if (!Array.isArray(players) || !players.every((name) => typeof name === "string")) {
        return null;
    }
    return players;
}

interface Placement {
    name: string;
    score: number;
}

function isPlacement(entry: unknown): entry is Placement {
    return (
        typeof entry === "object" &&
        entry !== null &&
        "name" in entry &&
        typeof entry.name === "string" &&
        "score" in entry &&
        typeof entry.score === "number"
    );
}

function readPlacements(message: Record<string, unknown>): Placement[] | null {
    const { result } = message;
    if (!Array.isArray(result) || !result.every(isPlacement)) {
        return null;
    }
    return result;
}

function describeGameEnd(message: Record<string, unknown>): string | null {
    const placements = message.end_reason === "completed" ? readPlacements(message) : null;
    if (placements !== null) {
        const results = placements.map(({ name, score }, index) =>
            t("tournament.chat.game_ended_place", { name, place: index + 1, score }),
        );
        return t("tournament.chat.game_ended", { results: formatList(results) });
    }
    const players = readNames(message);
    if (players === null) {
        return null;
    }
    return t("tournament.chat.game_ended_without_result", { players: formatList(players) });
}

function cancelReconnect(state: TournamentState): void {
    if (state.reconnectTimer !== null) {
        clearTimeout(state.reconnectTimer);
        state.reconnectTimer = null;
    }
}

function joinTournament(state: TournamentState, render: RenderTournament, wsUrl: string): void {
    state.connectionStatus = "connecting";
    render();
    state.socket?.connect(wsUrl);
}

function scheduleReconnect(
    state: TournamentState,
    render: RenderTournament,
    rejoin: () => void,
): void {
    if (state.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        state.connectionStatus = "disconnected";
        render();
        return;
    }
    const delay = Math.min(
        RECONNECT_FIRST_DELAY_MS * 2 ** state.reconnectAttempts,
        RECONNECT_MAX_DELAY_MS,
    );
    state.reconnectAttempts += 1;
    state.reconnecting = true;
    state.connectionStatus = "connecting";
    state.reconnectTimer = setTimeout(() => {
        state.reconnectTimer = null;
        rejoin();
    }, delay);
    render();
}

function buildStatusHandler(
    state: TournamentState,
    render: RenderTournament,
    rejoin: () => void,
): (status: SocketStatus) => void {
    return (status) => {
        if (status !== "connected" && isOnline(state) && state.reconnectTimer === null) {
            scheduleReconnect(state, render, rejoin);
            return;
        }
        state.connectionStatus = status;
        render();
    };
}

function reconnectOnResume(state: TournamentState, rejoin: () => void): void {
    if (!isOnline(state)) {
        return;
    }
    cancelReconnect(state);
    state.reconnectAttempts = 0;
    state.reconnecting = true;
    rejoin();
}

function buildMessageHandlers(state: TournamentState, render: RenderTournament): MessageHandlerMap {
    function appendChat(sender: string, text: string): void {
        state.chatMessages.push({ sender, text, timestamp: formatTime(new Date()) });
    }

    function endPage(code: string): void {
        cancelReconnect(state);
        state.pageError = code;
        render();
    }

    function onJoined(message: Record<string, unknown>): void {
        const reconnected = state.reconnecting;
        state.reconnecting = false;
        state.reconnectAttempts = 0;
        state.joined = true;
        state.players = readNames(message) ?? [];
        if (!reconnected) {
            appendChat(LOG_TYPE_SYSTEM, t("tournament.chat.you_joined"));
        }
        render();
    }

    function onPresence(message: Record<string, unknown>): void {
        const players = readNames(message);
        if (players === null) {
            return;
        }
        for (const name of players.filter((player) => !state.players.includes(player))) {
            appendChat(LOG_TYPE_SYSTEM, t("tournament.chat.player_joined", { name }));
        }
        for (const name of state.players.filter((player) => !players.includes(player))) {
            appendChat(LOG_TYPE_SYSTEM, t("tournament.chat.player_left", { name }));
        }
        state.players = players;
        render();
    }

    function onChat(message: Record<string, unknown>): void {
        const sender = readString(message, "player_name");
        const text = readString(message, "text");
        if (sender === null || text === null) {
            return;
        }
        appendChat(sender, text);
        render();
    }

    function onError(message: Record<string, unknown>): void {
        const code = message.message;
        if (
            !state.joined ||
            state.reconnecting ||
            code === OCCUPANCY.REPLACED_BY_NEW_CONNECTION ||
            code === TOURNAMENT_DELETED
        ) {
            endPage(String(code));
            return;
        }
        appendChat(LOG_TYPE_SYSTEM, describeTournamentError(code));
        render();
    }

    function onGameStarted(message: Record<string, unknown>): void {
        const players = readNames(message);
        if (players === null) {
            return;
        }
        state.players = state.players.filter((name) => !players.includes(name));
        appendChat(
            LOG_TYPE_SYSTEM,
            t("tournament.chat.game_started", { players: formatList(players) }),
        );
        render();
    }

    function onGameEnded(message: Record<string, unknown>): void {
        const line = describeGameEnd(message);
        if (line === null) {
            return;
        }
        appendChat(LOG_TYPE_SYSTEM, line);
        render();
    }

    function onGameStarting(message: Record<string, unknown>): void {
        state.socket?.disconnect();
        const start = readGameStart(message);
        if (!start) {
            endPage(PAGE_ERROR.GAME_START_INVALID);
            return;
        }
        cancelReconnect(state);
        appendChat(LOG_TYPE_SYSTEM, t("tournament.chat.game_starting"));
        render();
        enterGame(start);
    }

    return {
        chat: onChat,
        error: onError,
        game_ended: onGameEnded,
        game_started: onGameStarted,
        game_starting: onGameStarting,
        joined: onJoined,
        presence: onPresence,
    };
}

function handleMessage(handlers: MessageHandlerMap, message: Record<string, unknown>): void {
    const handler = handlers[String(message.type)];
    if (handler) {
        handler(message);
    }
}

function sendChat(state: TournamentState, text: string): boolean {
    const trimmed = text.trim();
    if (!trimmed || !state.socket || !isLive(state)) {
        return false;
    }
    return state.socket.send({ text: trimmed, type: "chat" });
}

function leaveOnPageExit(state: TournamentState): void {
    cancelReconnect(state);
    state.socket?.disconnect();
}

function rejoinOnPageShow(state: TournamentState, rejoin: () => void): void {
    if (state.pageError) {
        return;
    }
    cancelReconnect(state);
    Object.assign(state, createTournamentState(), { socket: state.socket });
    rejoin();
}

export {
    RESUME_RECONNECT_AFTER_HIDDEN_MS,
    TOURNAMENT_ERROR_CODES,
    buildMessageHandlers,
    buildStatusHandler,
    describeTournamentError,
    handleMessage,
    joinTournament,
    leaveOnPageExit,
    reconnectOnResume,
    rejoinOnPageShow,
    sendChat,
};
