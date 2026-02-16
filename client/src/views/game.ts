import {
    ClientMessageType,
    ConnectionStatus,
    EventType,
    GameAction,
    LOG_TYPE_SYSTEM,
    LOG_TYPE_UNKNOWN,
} from "../protocol";
import { type TemplateResult, html, render } from "lit-html";
import { consumeHandoff, drainBufferedMessages, setActiveSocket } from "../socket-handoff";
import type { GameSocket } from "../websocket";
import { clearSessionData } from "../session-storage";
import { navigate } from "../router";

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

function activateHandoffSocket(handoffSocket: GameSocket): void {
    socket = handoffSocket;
    connectionStatus = handoffSocket.isOpen
        ? ConnectionStatus.CONNECTED
        : ConnectionStatus.DISCONNECTED;
    setActiveSocket(handoffSocket);

    // Rebind handlers synchronously so no messages are lost between
    // consumeHandoff() and the next event-loop tick.
    bindGameHandlers();

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

export function gameView(gameId: string): TemplateResult {
    // reset state for this view
    logs = [];
    connectionStatus = ConnectionStatus.DISCONNECTED;
    currentGameId = gameId;
    const generation = ++viewGeneration;

    // try to acquire socket from room handoff
    const handoffResult = initHandoff(gameId, generation);
    if (handoffResult) {
        return handoffResult;
    }

    // no handoff available - direct game URLs are not supported after room migration
    return redirectToLobby(gameId);
}

// no handoff socket means direct navigation - redirect to lobby
function redirectToLobby(gameId: string): TemplateResult {
    clearSessionData(gameId);
    setTimeout(() => navigate("/"), 0);
    return html`
        <p>Redirecting to lobby...</p>
    `;
}

function handleGameMessage(message: Record<string, unknown>): void {
    appendLog({
        raw: JSON.stringify(message, null, 2),
        timestamp: new Date().toLocaleTimeString(),
        type: String(message.type || LOG_TYPE_UNKNOWN),
    });
    updateLogPanel();

    // auto-confirm round advancement after a short delay
    if (message.type === EventType.ROUND_END && socket) {
        const currentSocket = socket;
        setTimeout(() => {
            currentSocket.send({
                action: GameAction.CONFIRM_ROUND,
                type: ClientMessageType.GAME_ACTION,
            });
        }, 1000);
    }
}

function bindGameHandlers(): void {
    if (!socket) {
        return;
    }

    socket.setHandlers(
        (message) => handleGameMessage(message),
        (status) => {
            connectionStatus = status;
            updateStatusDisplay();
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
    if (socket) {
        socket.disconnect();
        socket = null;
    }
    logs = [];
}

function handleLeaveGame(): void {
    clearSessionData(currentGameId);
    // router calls cleanupGameView via route cleanup on navigation
    navigate("/");
}
