import { type NavigateOptions } from "@ronin/shared/router";

import { type ApiResult, apiGet, apiPost } from "@/api";
import { type ChatEntry, LOG_TYPE_SYSTEM } from "@/chat";
import { type MessageKey, formatList, formatTime, reportI18nError, t } from "@/i18n";
import { type SocketStatus, readString } from "@/lobby-socket";
import { OCCUPANCY } from "@/occupancy-errors";
import { enterGame, readGameStart } from "@/session";
import {
    PAGE_ERROR,
    TOURNAMENT_NOT_FOUND,
    type TournamentConfigAnswer,
    type TournamentState,
    createTournamentState,
    isLive,
    isOnline,
    parseRenamedName,
    readTournamentConfigAnswer,
} from "@/tournament/state";

type RenderTournament = () => void;

type Navigate = (url: string, options?: NavigateOptions) => void;

interface OwnerContext {
    readonly isDisposed: () => boolean;
    readonly navigate: Navigate;
    readonly render: RenderTournament;
    readonly tournamentId: string;
}

type MessageHandlerMap = Record<string, (msg: Record<string, unknown>) => void>;

const RECONNECT_FIRST_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 15_000;
const MAX_RECONNECT_ATTEMPTS = 24;
const RESUME_RECONNECT_AFTER_HIDDEN_MS = 20_000;

const TOURNAMENT_DELETED = "tournament_deleted";

const TOURNAMENT_ERROR_CODES = [
    "rate_limited",
    TOURNAMENT_NOT_FOUND,
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

function describeGameStart(players: readonly string[]): string {
    return t("tournament.chat.game_started", { players: formatList(players) });
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

type HistoryLine = Pick<ChatEntry, "sender" | "text">;

function systemLine(text: string | null): HistoryLine | null {
    return text === null ? null : { sender: LOG_TYPE_SYSTEM, text };
}

function presenceLine(entry: Record<string, unknown>, key: MessageKey): HistoryLine | null {
    const name = readString(entry, "player_name");
    return systemLine(name === null ? null : t(key, { name }));
}

const HISTORY_LINES: Record<string, (entry: Record<string, unknown>) => HistoryLine | null> = {
    chat: (entry) => {
        const sender = readString(entry, "player_name");
        const text = readString(entry, "text");
        return sender === null || text === null ? null : { sender, text };
    },
    game_ended: (entry) => systemLine(describeGameEnd(entry)),
    game_started: (entry) => {
        const players = readNames(entry);
        return systemLine(players === null ? null : describeGameStart(players));
    },
    player_offline: (entry) => presenceLine(entry, "tournament.chat.player_left"),
    player_online: (entry) => presenceLine(entry, "tournament.chat.player_joined"),
};

function readHistoryEntry(entry: unknown): ChatEntry | null {
    if (!isRecord(entry) || typeof entry.time !== "number") {
        return null;
    }
    const line = HISTORY_LINES[String(entry.type)]?.(entry) ?? null;
    return line === null ? null : { ...line, timestamp: formatTime(new Date(entry.time * 1000)) };
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

function showHistory(
    state: TournamentState,
    render: RenderTournament,
    message: Record<string, unknown>,
): void {
    const { messages } = message;
    if (!Array.isArray(messages)) {
        return;
    }
    state.chatMessages = messages
        .map(readHistoryEntry)
        .filter((entry): entry is ChatEntry => entry !== null);
    render();
}

function buildMessageHandlers(state: TournamentState, render: RenderTournament): MessageHandlerMap {
    function appendChat(sender: string, text: string, at = new Date()): void {
        state.chatMessages.push({ sender, text, timestamp: formatTime(at) });
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
        const { time } = message;
        appendChat(sender, text, typeof time === "number" ? new Date(time * 1000) : new Date());
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
        appendChat(LOG_TYPE_SYSTEM, describeGameStart(players));
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
        history: (message) => {
            showHistory(state, render, message);
        },
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
    Object.assign(state, createTournamentState(), { name: state.name, socket: state.socket });
    rejoin();
}

function tournamentApiPath(tournamentId: string): string {
    return `/api/lobby/tournaments/${encodeURIComponent(tournamentId)}`;
}

async function fetchTournamentConfig(tournamentId: string): Promise<TournamentConfigAnswer> {
    const result = await apiGet(tournamentApiPath(tournamentId));
    const answer = readTournamentConfigAnswer(result);
    if (answer.kind === "failed") {
        console.error("tournament config not loaded", result.ok ? "invalid answer" : result.error);
    }
    return answer;
}

function startOwnerAction(state: TournamentState, render: RenderTournament): boolean {
    if (state.ownerBusy) {
        return false;
    }
    state.ownerBusy = true;
    state.ownerError = null;
    render();
    return true;
}

async function renameTournament(
    state: TournamentState,
    context: OwnerContext,
    name: string,
): Promise<void> {
    if (!startOwnerAction(state, context.render)) {
        return;
    }
    const result = await apiPost(`${tournamentApiPath(context.tournamentId)}/rename`, { name });
    if (!context.isDisposed()) {
        showRenamed(state, result);
        context.render();
    }
}

function showRenamed(state: TournamentState, result: ApiResult): void {
    state.ownerBusy = false;
    const renamed = result.ok ? parseRenamedName(result.data) : null;
    if (renamed === null) {
        console.error("tournament not renamed", result.ok ? "invalid answer" : result.error);
        state.ownerError = "tournament.owner.rename_failed";
        return;
    }
    state.name = renamed;
}

async function deleteTournament(state: TournamentState, context: OwnerContext): Promise<void> {
    if (!startOwnerAction(state, context.render)) {
        return;
    }
    const result = await apiPost(`${tournamentApiPath(context.tournamentId)}/delete`, {});
    if (!context.isDisposed()) {
        leaveDeleted(state, context, result);
    }
}

function leaveDeleted(state: TournamentState, context: OwnerContext, result: ApiResult): void {
    state.ownerBusy = false;
    if (result.ok) {
        context.navigate("/", { replace: true });
        return;
    }
    console.error("tournament not deleted", result.error);
    state.ownerError = "tournament.owner.delete_failed";
    context.render();
}

export {
    RESUME_RECONNECT_AFTER_HIDDEN_MS,
    TOURNAMENT_ERROR_CODES,
    buildMessageHandlers,
    buildStatusHandler,
    deleteTournament,
    describeTournamentError,
    fetchTournamentConfig,
    handleMessage,
    joinTournament,
    leaveOnPageExit,
    reconnectOnResume,
    rejoinOnPageShow,
    renameTournament,
    sendChat,
};
export type { Navigate, OwnerContext };
