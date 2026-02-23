import {
    ClientMessageType,
    ConnectionStatus,
    EventType,
    GameAction,
    LOG_TYPE_SYSTEM,
    LOG_TYPE_UNKNOWN,
    SessionMessageType,
} from "../protocol";
import { type TemplateResult, html, render } from "lit-html";
import { clearGameSession, clearSessionData, getGameSession } from "../session-storage";
import { GameSocket } from "../websocket";
import { getLobbyUrl } from "../env";

interface LogEntry {
    raw: string;
    timestamp: string;
    type: string;
}

const MAX_LOG_ENTRIES = 500;

/** Connection state machine:
 *  JOINING  → initial connection, sends JOIN_GAME
 *  PLAYING  → game joined successfully, game events flowing
 *  (on disconnect while PLAYING → auto-reconnect sends RECONNECT, not JOIN_GAME)
 */
type GameConnectionState = "joining" | "playing";

let socket: GameSocket | null = null;
let logs: LogEntry[] = [];
let connectionStatus = ConnectionStatus.DISCONNECTED;
let currentGameId = "";
// incremented on each gameView call, checked in deferred setup
// to prevent orphaned connections after rapid navigation
let viewGeneration = 0;

let joinGameTicket = "";
let gameConnectionState: GameConnectionState = "joining";

let isReconnecting = false;
let reconnectGameTicket = "";
let reconnectRetryTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectRetryCount = 0;
const MAX_RECONNECT_RETRIES = 15;

function appendLog(entry: LogEntry): void {
    logs.push(entry);
    if (logs.length > MAX_LOG_ENTRIES) {
        logs = logs.slice(-MAX_LOG_ENTRIES);
    }
}

function resetGameState(gameId: string): number {
    logs = [];
    connectionStatus = ConnectionStatus.DISCONNECTED;
    currentGameId = gameId;
    reconnectRetryCount = 0;
    joinGameTicket = "";
    gameConnectionState = "joining";
    return ++viewGeneration;
}

export function gameView(gameId: string): TemplateResult {
    const generation = resetGameState(gameId);

    const session = getGameSession(gameId);
    if (session) {
        setTimeout(() => {
            if (viewGeneration !== generation) {
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
    if (!socket) {
        return;
    }
    // game_id is derived from the WebSocket URL path (/ws/{game_id}),
    // so the client only sends game_ticket and message type.
    socket.send({
        game_ticket: joinGameTicket,
        t: ClientMessageType.JOIN_GAME,
    });
}

function sendReconnectMessage(): void {
    if (isReconnecting || !socket) {
        return;
    }
    isReconnecting = true;
    // game_id is derived from the WebSocket URL path, same as JOIN_GAME.
    socket.send({
        game_ticket: reconnectGameTicket,
        t: ClientMessageType.RECONNECT,
    });
}

/** Check if a message is a response to a JOIN_GAME request. */
function isJoinGameResponse(message: Record<string, unknown>): boolean {
    if (message.type === SessionMessageType.ERROR) {
        const code = String(message.code || "");
        return code.startsWith("join_game_");
    }
    return false;
}

/** Check if a message is a reconnect response (success or error). */
function isReconnectResponse(message: Record<string, unknown>): boolean {
    if (message.type === SessionMessageType.GAME_RECONNECTED) {
        return true;
    }
    if (message.type === SessionMessageType.ERROR) {
        const code = String(message.code || "");
        return code.startsWith("reconnect_") || code === "invalid_ticket";
    }
    return false;
}

function attemptConnection(wsUrl: string, gameTicket: string): void {
    joinGameTicket = gameTicket;
    reconnectGameTicket = gameTicket;
    gameConnectionState = "joining";

    socket = new GameSocket(
        (message) => {
            // Detect successful join → transition to "playing" state
            if (gameConnectionState === "joining" && !isJoinGameResponse(message)) {
                gameConnectionState = "playing";
            }
            if (isReconnectResponse(message)) {
                isReconnecting = false;
            }
            handleGameMessage(message);
        },
        (status) => {
            connectionStatus = status;
            updateStatusDisplay();
            if (status === ConnectionStatus.CONNECTED) {
                // State machine determines which identity message to send:
                // - "joining": first connection or JOIN_GAME retry → send JOIN_GAME
                // - "playing": reconnect after network drop → send RECONNECT
                if (gameConnectionState === "joining") {
                    sendJoinGameMessage();
                } else {
                    sendReconnectMessage();
                }
            }
            if (status === ConnectionStatus.DISCONNECTED) {
                isReconnecting = false;
            }
        },
    );

    // enableReconnect handles automatic WebSocket reconnection on network drops.
    // The status callback above decides JOIN_GAME vs RECONNECT based on gameConnectionState.
    socket.enableReconnect(wsUrl);
    socket.connect(wsUrl);
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

function handleReconnected(message: Record<string, unknown>): void {
    clearReconnectRetryTimer();
    reconnectRetryCount = 0;
    appendLog({
        raw: JSON.stringify(message, null, 2),
        timestamp: new Date().toLocaleTimeString(),
        type: LOG_TYPE_SYSTEM,
    });
    appendLog({
        raw: `Reconnected to game at seat ${message.s}`,
        timestamp: new Date().toLocaleTimeString(),
        type: LOG_TYPE_SYSTEM,
    });
    updateLogPanel();
}

function clearReconnectRetryTimer(): void {
    if (reconnectRetryTimer !== null) {
        clearTimeout(reconnectRetryTimer);
        reconnectRetryTimer = null;
    }
}

function scheduleReconnectRetry(): void {
    if (reconnectRetryCount >= MAX_RECONNECT_RETRIES) {
        redirectOnPermanentError();
        return;
    }
    reconnectRetryCount++;
    clearReconnectRetryTimer();
    reconnectRetryTimer = setTimeout(() => {
        reconnectRetryTimer = null;
        isReconnecting = false;
        sendReconnectMessage();
    }, 1000);
}

function redirectOnPermanentError(): void {
    clearReconnectRetryTimer();
    if (socket) {
        socket.disableReconnect();
    }
    clearGameSession(currentGameId);
    clearSessionData(currentGameId);
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
        // Game already started — transition to reconnect flow.
        // The status handler already fired CONNECTED (which sent JOIN_GAME),
        // so we send RECONNECT immediately on the current connection.
        gameConnectionState = "playing";
        sendReconnectMessage();
        return true;
    }
    // Other join_game errors are permanent (not_found, no_session)
    redirectOnPermanentError();
    return true;
}

function autoConfirmRoundEnd(): void {
    if (!socket) {
        return;
    }
    const currentSocket = socket;
    setTimeout(() => {
        currentSocket.send({
            a: GameAction.CONFIRM_ROUND,
            t: ClientMessageType.GAME_ACTION,
        });
    }, 1000);
}

function handleSessionMessage(message: Record<string, unknown>): boolean {
    if (message.type === SessionMessageType.GAME_RECONNECTED) {
        handleReconnected(message);
        return true;
    }
    if (message.type === SessionMessageType.ERROR) {
        const code = String(message.code || "");
        if (code.startsWith("reconnect_") || code === "invalid_ticket") {
            return handleReconnectError(code);
        }
        if (code.startsWith("join_game_")) {
            return handleJoinGameError(code);
        }
    }
    return false;
}

function handleGameMessage(message: Record<string, unknown>): void {
    if (handleSessionMessage(message)) {
        return;
    }

    const eventType = message.t as number;
    appendLog({
        raw: JSON.stringify(message, null, 2),
        timestamp: new Date().toLocaleTimeString(),
        type: String(eventType ?? LOG_TYPE_UNKNOWN),
    });
    updateLogPanel();

    if (eventType === EventType.ROUND_END) {
        autoConfirmRoundEnd();
    }
}

function renderGameView(gameId: string): TemplateResult {
    return html`
        <div class="game">
            <div class="game-header">
                <button class="btn btn-secondary" @click=${handleLeaveGame}>Back to Lobby</button>
                <h2>Game: ${gameId}</h2>
                <span class="connection-status" id="connection-status">${connectionStatus}</span>
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
        ${logs.map(
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
        el.textContent = connectionStatus;
        el.className = `connection-status status-${connectionStatus}`;
    }
}

function resetConnectionState(): void {
    clearReconnectRetryTimer();
    isReconnecting = false;
    reconnectGameTicket = "";
    joinGameTicket = "";
    gameConnectionState = "joining";
    reconnectRetryCount = 0;
}

export function cleanupGameView(): void {
    viewGeneration++;
    resetConnectionState();
    if (socket) {
        socket.disableReconnect();
        socket.disconnect();
        socket = null;
    }
    logs = [];
}

function handleLeaveGame(): void {
    if (socket) {
        socket.disableReconnect();
        socket.disconnect();
        socket = null;
    }
    clearGameSession(currentGameId);
    clearSessionData(currentGameId);
    window.location.replace(getLobbyUrl());
}
