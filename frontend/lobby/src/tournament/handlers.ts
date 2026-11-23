import { type NavigateOptions } from "@ronin/shared/router";

import { type ApiResult, apiGet, apiPost } from "@/api";
import { type ChatEntry, LOG_TYPE_SYSTEM } from "@/chat";
import { readCurrentGame, readCurrentGames, readEpochTime, readNames } from "@/current-games";
import { type MessageKey, formatTime, reportI18nError, t } from "@/i18n";
import { type SocketStatus, readString } from "@/lobby-socket";
import { OCCUPANCY } from "@/occupancy-errors";
import { enterGame, readGameStart } from "@/session";
import { addPlayedGame, readPlayedGame, readPlayedGames } from "@/tournament/played-games";
import {
    PAGE_ERROR,
    TOURNAMENT_NOT_FOUND,
    type TournamentConfigAnswer,
    type TournamentState,
    createTournamentState,
    isFinished,
    isLive,
    isOnline,
    parseFinishedAt,
    parseRenamedName,
    readTournamentConfigAnswer,
} from "@/tournament/state";

type RenderTournament = () => void;

type Navigate = (url: string, options?: NavigateOptions) => void;

interface OwnerContext {
    readonly isDisposed: () => boolean;
    readonly navigate: Navigate;
    readonly reload: () => void;
    readonly render: RenderTournament;
    readonly tournamentId: string;
}

type MessageHandlerMap = Record<string, (msg: Record<string, unknown>) => void>;

const RECONNECT_FIRST_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 15_000;
const MAX_RECONNECT_ATTEMPTS = 24;
const RESUME_RECONNECT_AFTER_HIDDEN_MS = 20_000;

const TOURNAMENT_DELETED = "tournament_deleted";
const TOURNAMENT_FINISHED = "tournament_finished";

const TOURNAMENT_ERROR_CODES = [
    "rate_limited",
    TOURNAMENT_NOT_FOUND,
    TOURNAMENT_DELETED,
    TOURNAMENT_FINISHED,
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

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readHistoryChat(entry: unknown): ChatEntry | null {
    if (!isRecord(entry) || typeof entry.time !== "number") {
        return null;
    }
    const sender = readString(entry, "player_name");
    const text = readString(entry, "text");
    if (sender === null || text === null) {
        return null;
    }
    return { sender, text, timestamp: formatTime(new Date(entry.time * 1000)) };
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
        .map(readHistoryChat)
        .filter((entry): entry is ChatEntry => entry !== null);
    render();
}

function showFinished(state: TournamentState, render: RenderTournament, reload: () => void): void {
    cancelReconnect(state);
    state.finishedAt ??= new Date();
    render();
    reload();
}

function buildMessageHandlers(
    state: TournamentState,
    render: RenderTournament,
    reload: () => void,
): MessageHandlerMap {
    function appendChat(sender: string, text: string, at = new Date()): void {
        state.chatMessages.push({ sender, text, timestamp: formatTime(at) });
    }

    function endPage(code: string): void {
        cancelReconnect(state);
        state.pageError = code;
        render();
    }

    function onJoined(message: Record<string, unknown>): void {
        state.reconnecting = false;
        state.reconnectAttempts = 0;
        state.joined = true;
        state.players = readNames(message) ?? [];
        state.games = readCurrentGames(message);
        state.played = readPlayedGames(message);
        render();
    }

    function onPresence(message: Record<string, unknown>): void {
        const players = readNames(message);
        if (players === null) {
            return;
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
        if (!state.chatOpen) {
            state.chatUnread += 1;
        }
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
        const game = readCurrentGame(message, readEpochTime(message.time));
        if (game !== null) {
            state.games = [...state.games, game];
        }
        render();
    }

    function onGameEnded(message: Record<string, unknown>): void {
        state.games = state.games.filter((game) => game.gameId !== message.game_id);
        const played = readPlayedGame(message);
        if (played !== null) {
            state.played = addPlayedGame(state.played, played);
        }
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
        render();
        enterGame(start);
    }

    return {
        chat: onChat,
        error: (message) => {
            if (message.message === TOURNAMENT_FINISHED) {
                showFinished(state, render, reload);
                return;
            }
            onError(message);
        },
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
    if (state.pageError || isFinished(state)) {
        return;
    }
    cancelReconnect(state);
    Object.assign(state, createTournamentState(), {
        name: state.name,
        socket: state.socket,
        tab: state.tab,
    });
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

async function finishTournament(state: TournamentState, context: OwnerContext): Promise<void> {
    if (!startOwnerAction(state, context.render)) {
        return;
    }
    const result = await apiPost(`${tournamentApiPath(context.tournamentId)}/finish`, {});
    if (!context.isDisposed()) {
        showFinishAnswer(state, context, result);
    }
}

function showFinishAnswer(state: TournamentState, context: OwnerContext, result: ApiResult): void {
    state.ownerBusy = false;
    const finishedAt = result.ok ? parseFinishedAt(result.data) : null;
    if (finishedAt === null) {
        console.error("tournament not finished", result.ok ? "invalid answer" : result.error);
        state.ownerError = "tournament.owner.finish_failed";
        context.render();
        return;
    }
    state.finishedAt = finishedAt;
    context.render();
    context.reload();
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
        context.navigate("/tournaments", { replace: true });
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
    finishTournament,
    handleMessage,
    joinTournament,
    leaveOnPageExit,
    reconnectOnResume,
    rejoinOnPageShow,
    renameTournament,
    sendChat,
};
export type { Navigate, OwnerContext };
