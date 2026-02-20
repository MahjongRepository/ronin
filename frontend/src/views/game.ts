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
import {
    clearGameSession,
    clearSessionData,
    getGameSession,
    getGameTicket,
    storeGameSession,
} from "../session-storage";
import { consumeHandoff, drainBufferedMessages, setActiveSocket } from "../socket-handoff";
import { GameSocket } from "../websocket";
import { getLobbyUrl } from "../env";

interface LogEntry {
    raw: string;
    timestamp: string;
    type: string;
}

const MAX_LOG_ENTRIES = 500;

let socket: GameSocket | null = null;
let logs: LogEntry[] = [];
let connectionStatus = ConnectionStatus.DISCONNECTED;
let currentGameId = "";
// incremented on each gameView call, checked in deferred setup
// to prevent orphaned connections after rapid navigation
let viewGeneration = 0;

function appendLog(entry: LogEntry): void {
    logs.push(entry);
    if (logs.length > MAX_LOG_ENTRIES) {
        logs = logs.slice(-MAX_LOG_ENTRIES);
    }
}

function persistGameSessionFromStorage(): void {
    const wsUrl = sessionStorage.getItem("ws_url");
    const gameTicket = getGameTicket();
    if (wsUrl && gameTicket) {
        storeGameSession(currentGameId, wsUrl, gameTicket);
    }
}

function enableAutoReconnectFromStorage(): void {
    const wsUrl = sessionStorage.getItem("ws_url");
    const gameTicket = getGameTicket();
    if (wsUrl && gameTicket && socket) {
        reconnectGameTicket = gameTicket;
        socket.enableReconnect(wsUrl, sendReconnectMessage);
    }
}

function activateHandoffSocket(handoffSocket: GameSocket): void {
    socket = handoffSocket;
    connectionStatus = handoffSocket.isOpen
        ? ConnectionStatus.CONNECTED
        : ConnectionStatus.DISCONNECTED;
    setActiveSocket(handoffSocket);
    persistGameSessionFromStorage();

    // Rebind handlers synchronously so no messages are lost between
    // consumeHandoff() and the next event-loop tick.
    bindGameHandlers();
    enableAutoReconnectFromStorage();

    // Replay any messages that arrived during the handoff window
    // (between beginHandoff in room view and bindGameHandlers above).
    // Process through handleGameMessage so game logic (e.g. auto-confirm
    // on round_end) runs for buffered messages, not just logging.
    for (const msg of drainBufferedMessages()) {
        handleGameMessage(msg);
    }

    appendLog({
        raw: "Transitioned from room to game",
        timestamp: new Date().toLocaleTimeString(),
        type: LOG_TYPE_SYSTEM,
    });
}

function initHandoff(gameId: string, generation: number): TemplateResult | null {
    const handoffSocket = consumeHandoff(gameId);
    if (!handoffSocket) {
        return null;
    }

    activateHandoffSocket(handoffSocket);

    // Defer DOM update until the view template has been rendered.
    setTimeout(() => {
        if (viewGeneration !== generation) {
            return;
        }
        updateLogPanel();
    }, 0);

    return renderGameView(gameId);
}

function resetGameState(gameId: string): number {
    logs = [];
    connectionStatus = ConnectionStatus.DISCONNECTED;
    currentGameId = gameId;
    reconnectRetryCount = 0;
    return ++viewGeneration;
}

function tryReconnectFromSession(gameId: string, generation: number): TemplateResult | null {
    const session = getGameSession(gameId);
    if (!session) {
        return null;
    }
    setTimeout(() => {
        if (viewGeneration !== generation) {
            return;
        }
        attemptReconnection(session.wsUrl, session.gameTicket);
    }, 0);
    return renderGameView(gameId);
}

export function gameView(gameId: string): TemplateResult {
    const generation = resetGameState(gameId);

    // try to acquire socket from room handoff
    const handoffResult = initHandoff(gameId, generation);
    if (handoffResult) {
        return handoffResult;
    }

    // no handoff — attempt reconnection from stored session
    return tryReconnectFromSession(gameId, generation) ?? redirectToLobby(gameId);
}

// no handoff socket means direct navigation - redirect to lobby
function redirectToLobby(gameId: string): TemplateResult {
    clearSessionData(gameId);
    setTimeout(() => {
        window.location.replace(getLobbyUrl());
    }, 0);
    return html`
        <p>Redirecting to lobby...</p>
    `;
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

let isReconnecting = false;
let reconnectGameTicket = "";
let reconnectRetryTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectRetryCount = 0;
const MAX_RECONNECT_RETRIES = 15;

function sendReconnectMessage(): void {
    if (isReconnecting || !socket) {
        return;
    }
    isReconnecting = true;
    socket.send({
        game_ticket: reconnectGameTicket,
        room_id: currentGameId,
        type: ClientMessageType.RECONNECT,
    });
}

function attemptReconnection(wsUrl: string, gameTicket: string): void {
    reconnectGameTicket = gameTicket;

    socket = new GameSocket(
        (message) => {
            if (isReconnectResponse(message)) {
                isReconnecting = false;
            }
            handleGameMessage(message);
        },
        (status) => {
            connectionStatus = status;
            updateStatusDisplay();
            if (status === ConnectionStatus.CONNECTED) {
                sendReconnectMessage();
            }
            if (status === ConnectionStatus.DISCONNECTED) {
                isReconnecting = false;
            }
        },
    );

    setActiveSocket(socket);

    // Enable auto-reconnect for network drops
    socket.enableReconnect(wsUrl, sendReconnectMessage);

    socket.connect(wsUrl);
}

const PERMANENT_RECONNECT_CODES = new Set([
    "reconnect_no_session",
    "reconnect_no_seat",
    "reconnect_game_gone",
    "reconnect_game_mismatch",
    "reconnect_in_room",
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

function autoConfirmRoundEnd(): void {
    if (!socket) {
        return;
    }
    const currentSocket = socket;
    setTimeout(() => {
        currentSocket.send({
            action: GameAction.CONFIRM_ROUND,
            type: ClientMessageType.GAME_ACTION,
        });
    }, 1000);
}

function handleSessionMessage(message: Record<string, unknown>): boolean {
    if (message.type === SessionMessageType.GAME_RECONNECTED) {
        handleReconnected(message);
        return true;
    }
    if (message.type === SessionMessageType.ERROR && isReconnectResponse(message)) {
        return handleReconnectError(String(message.code));
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

function bindGameHandlers(): void {
    if (!socket) {
        return;
    }

    socket.setHandlers(
        (message) => {
            if (isReconnectResponse(message)) {
                isReconnecting = false;
            }
            handleGameMessage(message);
        },
        (status) => {
            connectionStatus = status;
            updateStatusDisplay();
            if (status === ConnectionStatus.CONNECTED && reconnectGameTicket) {
                sendReconnectMessage();
            }
            if (status === ConnectionStatus.DISCONNECTED) {
                isReconnecting = false;
            }
        },
    );
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

export function cleanupGameView(): void {
    viewGeneration++;
    clearReconnectRetryTimer();
    isReconnecting = false;
    reconnectGameTicket = "";
    reconnectRetryCount = 0;
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
