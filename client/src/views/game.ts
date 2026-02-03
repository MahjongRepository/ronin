import { type TemplateResult, html, render } from "lit-html";
import { GameSocket } from "../websocket";
import { navigate } from "../router";

interface LogEntry {
    raw: string;
    timestamp: string;
    type: string;
}

const MAX_LOG_ENTRIES = 500;

let socket: GameSocket | null = null;
let logs: LogEntry[] = [];
let connectionStatus = "disconnected";
// incremented on each gameView call, checked in deferred connectToGame
// to prevent orphaned connections after rapid navigation
let viewGeneration = 0;

function appendLog(entry: LogEntry): void {
    logs.push(entry);
    if (logs.length > MAX_LOG_ENTRIES) {
        logs = logs.slice(-MAX_LOG_ENTRIES);
    }
}

export function gameView(gameId: string): TemplateResult {
    const wsUrl = sessionStorage.getItem("ws_url");
    const playerName = sessionStorage.getItem("player_name");

    if (!wsUrl || !playerName || !wsUrl.includes(`/ws/${gameId}`)) {
        return redirectToLobby();
    }

    // reset state for fresh connection
    logs = [];
    connectionStatus = "disconnected";
    const generation = ++viewGeneration;

    // connect after render; bail if navigation happened before timeout fires
    setTimeout(() => {
        if (viewGeneration !== generation) {
            return;
        }
        connectToGame(wsUrl, gameId, playerName);
    }, 0);

    return renderGameView(gameId);
}

// no connection info or stale ws_url from a different game, redirect to lobby
function redirectToLobby(): TemplateResult {
    sessionStorage.removeItem("ws_url");
    sessionStorage.removeItem("player_name");
    setTimeout(() => navigate("/"), 0);
    return html`
        <p>Redirecting to lobby...</p>
    `;
}

function connectToGame(wsUrl: string, gameId: string, playerName: string): void {
    if (socket) {
        socket.disconnect();
    }

    socket = new GameSocket(
        (message) => {
            appendLog({
                raw: JSON.stringify(message, null, 2),
                timestamp: new Date().toLocaleTimeString(),
                type: String(message.type || "unknown"),
            });
            updateLogPanel();

            // auto-confirm round advancement after a short delay
            if (message.type === "round_end" && socket) {
                const currentSocket = socket;
                setTimeout(() => {
                    currentSocket.send({ action: "confirm_round", data: {}, type: "game_action" });
                }, 1000);
            }
        },
        (status) => {
            connectionStatus = status;
            updateStatusDisplay();

            // send join_game when connected
            if (status === "connected" && socket) {
                socket.send({
                    game_id: gameId,
                    player_name: playerName,
                    type: "join_game",
                });
                appendLog({
                    raw: `Sent join_game as "${playerName}"`,
                    timestamp: new Date().toLocaleTimeString(),
                    type: "system",
                });
                updateLogPanel();
            }
        },
    );

    socket.connect(wsUrl);
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
    sessionStorage.removeItem("ws_url");
    sessionStorage.removeItem("player_name");
    // router calls cleanupGameView via route cleanup on navigation
    navigate("/");
}
