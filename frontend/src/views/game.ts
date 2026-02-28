import {
    CONNECTION_STATUS,
    type ConnectionStatus,
    type GameReconnectedEvent,
    LOG_TYPE_SYSTEM,
    LOG_TYPE_UNKNOWN,
    type ParsedServerMessage,
    SESSION_MESSAGE_TYPE,
    buildConfirmRoundAction,
    buildJoinGameMessage,
    buildReconnectMessage,
    parseServerMessage,
} from "@/shared/protocol";
import { type TemplateResult, html, render } from "lit-html";
import { clearGameSession, clearSessionData, getGameSession } from "@/session-storage";
import { GameSocket } from "@/websocket";
import { getLobbyUrl } from "@/env";

interface LogEntry {
    raw: string;
    timestamp: string;
    type: string;
}

const MAX_LOG_ENTRIES = 500;

/** Connection state machine:
 *  JOINING  -> initial connection, sends JOIN_GAME
 *  PLAYING  -> game joined successfully, game events flowing
 *  (on disconnect while PLAYING -> auto-reconnect sends RECONNECT, not JOIN_GAME)
 */
type GameConnectionState = "joining" | "playing";

interface GameViewState {
    connectionStatus: ConnectionStatus;
    currentGameId: string;
    logs: LogEntry[];
    viewGeneration: number;
}

interface ConnectionState {
    gameConnectionState: GameConnectionState;
    isReconnecting: boolean;
    joinGameTicket: string;
    reconnectGameTicket: string;
    reconnectRetryCount: number;
    reconnectRetryTimer: ReturnType<typeof setTimeout> | null;
    socket: GameSocket | null;
}

function createInitialViewState(): GameViewState {
    return {
        connectionStatus: CONNECTION_STATUS.DISCONNECTED,
        currentGameId: "",
        logs: [],
        viewGeneration: 0,
    };
}

function createInitialConnectionState(): ConnectionState {
    return {
        gameConnectionState: "joining",
        isReconnecting: false,
        joinGameTicket: "",
        reconnectGameTicket: "",
        reconnectRetryCount: 0,
        reconnectRetryTimer: null,
        socket: null,
    };
}

let view = createInitialViewState();
let conn = createInitialConnectionState();

const MAX_RECONNECT_RETRIES = 15;

function appendLog(entry: LogEntry): void {
    view.logs.push(entry);
    if (view.logs.length > MAX_LOG_ENTRIES) {
        view.logs = view.logs.slice(-MAX_LOG_ENTRIES);
    }
}

function resetGameState(gameId: string): number {
    const nextGeneration = view.viewGeneration + 1;
    view = {
        ...createInitialViewState(),
        currentGameId: gameId,
        viewGeneration: nextGeneration,
    };
    conn.reconnectRetryCount = 0;
    conn.joinGameTicket = "";
    conn.gameConnectionState = "joining";
    return view.viewGeneration;
}

export function gameView(gameId: string): TemplateResult {
    const generation = resetGameState(gameId);

    const session = getGameSession(gameId);
    if (session) {
        setTimeout(() => {
            if (view.viewGeneration !== generation) {
                return;
            }
            attemptConnection(session.wsUrl, session.gameTicket);
        }, 0);
        return renderGameView(gameId);
    }

    return redirectToLobby(gameId);
}

function redirectToLobby(gameId: string): TemplateResult {
    clearSessionData(gameId);
    setTimeout(() => {
        window.location.replace(getLobbyUrl());
    }, 0);
    return html`
        <p>Redirecting to lobby...</p>
    `;
}

function sendJoinGameMessage(): void {
    if (!conn.socket) {
        return;
    }
    conn.socket.send(buildJoinGameMessage(conn.joinGameTicket));
}

function sendReconnectMessage(): void {
    if (conn.isReconnecting || !conn.socket) {
        return;
    }
    conn.isReconnecting = true;
    conn.socket.send(buildReconnectMessage(conn.reconnectGameTicket));
}

/** Check if a raw message is a response to a JOIN_GAME request. */
function isJoinGameResponse(message: Record<string, unknown>): boolean {
    if (message.type !== SESSION_MESSAGE_TYPE.ERROR) {
        return false;
    }
    const code = String(message.code || "");
    return code.startsWith("join_game_");
}

/** Check if a raw message is a reconnect response (success or error). */
function isReconnectResponse(message: Record<string, unknown>): boolean {
    if (message.type === SESSION_MESSAGE_TYPE.GAME_RECONNECTED) {
        return true;
    }
    if (message.type !== SESSION_MESSAGE_TYPE.ERROR) {
        return false;
    }
    const code = String(message.code || "");
    return code.startsWith("reconnect_") || code === "invalid_ticket";
}

function attemptConnection(wsUrl: string, gameTicket: string): void {
    conn.joinGameTicket = gameTicket;
    conn.reconnectGameTicket = gameTicket;
    conn.gameConnectionState = "joining";

    conn.socket = new GameSocket(
        (message) => {
            // Detect successful join -> transition to "playing" state
            if (conn.gameConnectionState === "joining" && !isJoinGameResponse(message)) {
                conn.gameConnectionState = "playing";
            }
            if (isReconnectResponse(message)) {
                conn.isReconnecting = false;
            }
            handleGameMessage(message);
        },
        (status) => {
            view.connectionStatus = status;
            updateStatusDisplay();
            if (status === CONNECTION_STATUS.CONNECTED) {
                // State machine determines which identity message to send:
                // - "joining": first connection or JOIN_GAME retry -> send JOIN_GAME
                // - "playing": reconnect after network drop -> send RECONNECT
                if (conn.gameConnectionState === "joining") {
                    sendJoinGameMessage();
                } else {
                    sendReconnectMessage();
                }
            }
            if (status === CONNECTION_STATUS.DISCONNECTED) {
                conn.isReconnecting = false;
            }
        },
    );

    // enableReconnect handles automatic WebSocket reconnection on network drops.
    // The status callback above decides JOIN_GAME vs RECONNECT based on gameConnectionState.
    conn.socket.enableReconnect(wsUrl);
    conn.socket.connect(wsUrl);
}

const PERMANENT_RECONNECT_CODES = new Set([
    "reconnect_no_session",
    "reconnect_no_seat",
    "reconnect_game_gone",
    "reconnect_game_mismatch",
    "reconnect_already_active",
    "reconnect_snapshot_failed",
    "invalid_ticket",
]);

function handleReconnected(parsed: GameReconnectedEvent): void {
    clearReconnectRetryTimer();
    conn.reconnectRetryCount = 0;
    appendLog({
        raw: JSON.stringify(parsed, null, 2),
        timestamp: new Date().toLocaleTimeString(),
        type: LOG_TYPE_SYSTEM,
    });
    appendLog({
        raw: `Reconnected to game at seat ${parsed.seat}`,
        timestamp: new Date().toLocaleTimeString(),
        type: LOG_TYPE_SYSTEM,
    });
    updateLogPanel();
}

function clearReconnectRetryTimer(): void {
    if (conn.reconnectRetryTimer !== null) {
        clearTimeout(conn.reconnectRetryTimer);
        conn.reconnectRetryTimer = null;
    }
}

function scheduleReconnectRetry(): void {
    if (conn.reconnectRetryCount >= MAX_RECONNECT_RETRIES) {
        redirectOnPermanentError();
        return;
    }
    conn.reconnectRetryCount++;
    clearReconnectRetryTimer();
    const delayMs = Math.min(1000 * 2 ** (conn.reconnectRetryCount - 1), 15_000);
    conn.reconnectRetryTimer = setTimeout(() => {
        conn.reconnectRetryTimer = null;
        conn.isReconnecting = false;
        sendReconnectMessage();
    }, delayMs);
}

function redirectOnPermanentError(): void {
    clearReconnectRetryTimer();
    if (conn.socket) {
        conn.socket.disableReconnect();
    }
    clearGameSession(view.currentGameId);
    clearSessionData(view.currentGameId);
    window.location.replace(getLobbyUrl());
}

function handleReconnectError(code: string): boolean {
    if (PERMANENT_RECONNECT_CODES.has(code)) {
        redirectOnPermanentError();
        return true;
    }
    if (code === "reconnect_retry_later") {
        scheduleReconnectRetry();
        return true;
    }
    return false;
}

function handleJoinGameError(code: string): boolean {
    if (code === "join_game_already_started") {
        // Game already started -- transition to reconnect flow.
        // The status handler already fired CONNECTED (which sent JOIN_GAME),
        // so we send RECONNECT immediately on the current connection.
        conn.gameConnectionState = "playing";
        sendReconnectMessage();
        return true;
    }
    // Other join_game errors are permanent (not_found, no_session)
    redirectOnPermanentError();
    return true;
}

function autoConfirmRoundEnd(): void {
    if (!conn.socket) {
        return;
    }
    const currentSocket = conn.socket;
    setTimeout(() => {
        currentSocket.send(buildConfirmRoundAction());
    }, 1000);
}

function handleSessionErrorCode(code: string): boolean {
    if (code.startsWith("reconnect_") || code === "invalid_ticket") {
        return handleReconnectError(code);
    }
    if (code.startsWith("join_game_")) {
        return handleJoinGameError(code);
    }
    // Server says player is not in any game — session state is inconsistent.
    // redirectOnPermanentError clears session storage and redirects to lobby,
    // which is the correct recovery for this state mismatch.
    if (code === "not_in_game") {
        redirectOnPermanentError();
        return true;
    }
    return false;
}

function handleParsedSessionMessage(parsed: ParsedServerMessage): boolean {
    if (parsed.type === "game_reconnected") {
        handleReconnected(parsed);
        return true;
    }
    if (parsed.type === "session_error") {
        return handleSessionErrorCode(parsed.code);
    }
    return false;
}

function logAndUpdate(raw: string, type: string): void {
    appendLog({ raw, timestamp: new Date().toLocaleTimeString(), type });
    updateLogPanel();
}

function handleGameMessage(message: Record<string, unknown>): void {
    const [error, parsed] = parseServerMessage(message);

    if (error) {
        const errorDetail = `Parse error: ${error.message}\n${JSON.stringify(message, null, 2)}`;
        logAndUpdate(errorDetail, LOG_TYPE_UNKNOWN);
        return;
    }

    if (handleParsedSessionMessage(parsed)) {
        return;
    }

    logAndUpdate(JSON.stringify(parsed, null, 2), parsed.type);

    if (parsed.type === "round_end") {
        autoConfirmRoundEnd();
    }
}

function renderGameView(gameId: string): TemplateResult {
    return html`
        <div class="game">
            <div class="game-header">
                <button class="secondary" @click=${handleLeaveGame}>Back to Lobby</button>
                <h2>Game: ${gameId}</h2>
                <span class="connection-status" id="connection-status">${view.connectionStatus}</span>
            </div>
            <div class="log-panel" id="log-panel">
                <div class="log-entries" id="log-entries"></div>
            </div>
        </div>
    `;
}

function updateLogPanel(): void {
    const container = document.getElementById("log-entries");
    if (!container) {
        return;
    }

    render(
        html`
        ${view.logs.map(
            (entry) => html`
            <div class="log-entry log-${entry.type}">
                <span class="log-time">[${entry.timestamp}]</span>
                <span class="log-type">${entry.type}</span>
                <pre class="log-raw">${entry.raw}</pre>
            </div>
        `,
        )}
    `,
        container,
    );

    // auto-scroll to bottom
    const panel = document.getElementById("log-panel");
    if (panel) {
        panel.scrollTop = panel.scrollHeight;
    }
}

function updateStatusDisplay(): void {
    const el = document.getElementById("connection-status");
    if (el) {
        el.textContent = view.connectionStatus;
        el.className = `connection-status status-${view.connectionStatus}`;
    }
}

/** Disconnect the socket and reset all connection state. */
function teardownConnection(): void {
    const { socket } = conn;
    clearReconnectRetryTimer();
    conn = createInitialConnectionState();
    if (socket) {
        socket.disableReconnect();
        socket.disconnect();
    }
}

export function cleanupGameView(): void {
    view.viewGeneration++;
    teardownConnection();
    view.logs = [];
}

function handleLeaveGame(): void {
    teardownConnection();
    clearGameSession(view.currentGameId);
    clearSessionData(view.currentGameId);
    window.location.replace(getLobbyUrl());
}
