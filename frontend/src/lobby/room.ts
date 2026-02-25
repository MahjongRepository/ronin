import { html, render } from "lit-html";
import { LobbySocket } from "./lobby-socket";
import { storeGameSession } from "../session-storage";

interface RoomConfig {
    roomId: string;
    wsUrl: string;
}

interface PlayerInfo {
    name: string;
    ready: boolean;
}

interface ChatEntry {
    sender: string;
    text: string;
    timestamp: string;
}

const LOG_TYPE_SYSTEM = "system";

let socket: LobbySocket | null = null;
let players: PlayerInfo[] = [];
let chatMessages: ChatEntry[] = [];
let connectionStatus: "connected" | "disconnected" | "error" = "disconnected";
let isReady = false;

type MessageHandlerMap = Record<string, (msg: Record<string, unknown>) => void>;
let messageHandlers: MessageHandlerMap = {};

function appendChat(sender: string, text: string): void {
    chatMessages.push({
        sender,
        text,
        timestamp: new Date().toLocaleTimeString(),
    });
    updateChatPanel();
}

function onRoomJoined(message: Record<string, unknown>): void {
    players = (message.players as PlayerInfo[]) ?? [];
    updatePlayerList();
    appendChat(LOG_TYPE_SYSTEM, "Joined room");
}

function onPlayerJoined(message: Record<string, unknown>): void {
    players = (message.players as PlayerInfo[]) ?? players;
    if (message.player_name) {
        appendChat(LOG_TYPE_SYSTEM, `${message.player_name} joined`);
    }
    updatePlayerList();
}

function onPlayerLeft(message: Record<string, unknown>): void {
    players = (message.players as PlayerInfo[]) ?? players;
    if (message.player_name) {
        appendChat(LOG_TYPE_SYSTEM, `${message.player_name} left`);
    }
    updatePlayerList();
}

function onPlayerReadyChanged(message: Record<string, unknown>): void {
    players = (message.players as PlayerInfo[]) ?? players;
    updatePlayerList();
}

function disconnectSocket(): void {
    if (socket) {
        socket.disconnect();
        socket = null;
    }
}

function onGameStarting(message: Record<string, unknown>): void {
    const gameId = message.game_id as string;
    const wsUrl = message.ws_url as string;
    const gameTicket = message.game_ticket as string;
    const gameClientUrl = (message.game_client_url as string) || "/game";

    if (gameId && wsUrl && gameTicket) {
        storeGameSession(gameId, wsUrl, gameTicket);
    }

    appendChat(LOG_TYPE_SYSTEM, "Game starting!");
    disconnectSocket();
    window.location.href = `${gameClientUrl}#/game/${gameId}`;
}

function buildMessageHandlers(): MessageHandlerMap {
    return {
        chat: (msg) => appendChat(msg.player_name as string, msg.text as string),
        error: (msg) => appendChat(LOG_TYPE_SYSTEM, `Error: ${msg.message}`),
        game_starting: onGameStarting,
        player_joined: onPlayerJoined,
        player_left: onPlayerLeft,
        player_ready_changed: onPlayerReadyChanged,
        pong: () => {},
        room_joined: onRoomJoined,
    };
}

function handleMessage(message: Record<string, unknown>): void {
    const handler = messageHandlers[message.type as string];
    if (handler) {
        handler(message);
    }
}

function updatePlayerList(): void {
    const container = document.getElementById("room-players");
    if (!container) {
        return;
    }

    render(
        html`
        ${players.map(
            (player) => html`
            <div class="room-player-item">
                <span class="room-player-status ${player.ready ? "ready" : "not-ready"}">${player.ready ? "\u2713" : "\u25CB"}</span>
                <span class="room-player-name">${player.name}</span>
            </div>
        `,
        )}
    `,
        container,
    );
}

function updateChatPanel(): void {
    const container = document.getElementById("room-chat-messages");
    if (!container) {
        return;
    }

    render(
        html`
        ${chatMessages.map(
            (msg) => html`
            <div class="room-chat-entry ${msg.sender === LOG_TYPE_SYSTEM ? "system" : ""}">
                <span class="room-chat-time">[${msg.timestamp}]</span>
                ${msg.sender !== LOG_TYPE_SYSTEM ? html`<span class="room-chat-sender">${msg.sender}:</span>` : null}
                <span class="room-chat-text">${msg.text}</span>
            </div>
        `,
        )}
    `,
        container,
    );

    container.scrollTop = container.scrollHeight;
}

function updateStatusDisplay(): void {
    const el = document.getElementById("connection-status");
    if (el) {
        el.textContent = connectionStatus;
        el.className = `connection-status status-${connectionStatus}`;
    }
}

function handleToggleReady(): void {
    if (!socket) {
        return;
    }
    isReady = !isReady;
    socket.send({ ready: isReady, type: "set_ready" });

    const btn = document.getElementById("ready-btn");
    if (btn) {
        btn.textContent = isReady ? "Not Ready" : "Ready";
        btn.className = `room-ready-btn ${isReady ? "secondary" : ""}`;
    }
}

function handleChatKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") {
        handleSendChat();
    }
}

function handleSendChat(): void {
    const input = document.getElementById("chat-input") as HTMLInputElement | null;
    if (!input || !socket) {
        return;
    }
    const text = input.value.trim();
    if (!text) {
        return;
    }
    socket.send({ text, type: "chat" });
    input.value = "";
}

function handleLeaveRoom(): void {
    if (socket) {
        socket.send({ type: "leave_room" });
    }
    disconnectSocket();
    window.location.href = "/";
}

function renderRoomUI(container: HTMLElement, roomId: string): void {
    render(
        html`
        <div class="room">
            <div class="room-header">
                <button class="secondary" @click=${handleLeaveRoom}>Leave Room</button>
                <h2>Room: ${roomId}</h2>
                <span class="connection-status" id="connection-status">${connectionStatus}</span>
            </div>
            <div class="room-content">
                <div class="room-players-panel">
                    <h3>Players</h3>
                    <div id="room-players"></div>
                    <button class="room-ready-btn" id="ready-btn" @click=${handleToggleReady}>
                        Ready
                    </button>
                </div>
                <div class="room-chat-panel">
                    <h3>Chat</h3>
                    <div class="room-chat-messages" id="room-chat-messages"></div>
                    <div class="room-chat-input">
                        <input type="text" id="chat-input" placeholder="Type a message..." @keydown=${handleChatKeydown} />
                        <button class="outline" @click=${handleSendChat}>Send</button>
                    </div>
                </div>
            </div>
        </div>
    `,
        container,
    );
}

function resetRoomState(): void {
    players = [];
    chatMessages = [];
    connectionStatus = "disconnected";
    isReady = false;
    messageHandlers = buildMessageHandlers();
}

export function initRoomPage(config: RoomConfig): void {
    const container = document.getElementById("room-app");
    if (!container) {
        return;
    }

    resetRoomState();
    renderRoomUI(container, config.roomId);

    socket = new LobbySocket(
        (message) => handleMessage(message),
        (status) => {
            connectionStatus = status;
            updateStatusDisplay();
        },
    );

    socket.connect(config.wsUrl);
}
