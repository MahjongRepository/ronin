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
    is_bot: boolean;
    is_owner: boolean;
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
let isOwner = false;
let canStart = false;
let currentPlayerName = "";

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

function getMyReadyState(): boolean {
    const me = players.find((player) => player.name === currentPlayerName && !player.is_bot);
    return me?.ready ?? false;
}

function updateFromServerState(message: Record<string, unknown>): void {
    players = (message.players as PlayerInfo[]) ?? players;
    canStart = (message.can_start as boolean) ?? false;
    // Derive isOwner from the authoritative player list as a fallback,
    // so ownership is corrected even if the owner_changed message was missed.
    const self = players.find((player) => player.name === currentPlayerName && !player.is_bot);
    if (self) {
        isOwner = self.is_owner;
    }
    updatePlayerList();
    updateActionButton();
}

function onRoomJoined(message: Record<string, unknown>): void {
    currentPlayerName = (message.player_name as string) ?? "";
    isOwner = (message.is_owner as boolean) ?? false;
    updateFromServerState(message);
    appendChat(LOG_TYPE_SYSTEM, "Joined room");
}

function onPlayerJoined(message: Record<string, unknown>): void {
    updateFromServerState(message);
    if (message.player_name) {
        appendChat(LOG_TYPE_SYSTEM, `${message.player_name} joined`);
    }
}

function onPlayerLeft(message: Record<string, unknown>): void {
    updateFromServerState(message);
    if (message.player_name) {
        appendChat(LOG_TYPE_SYSTEM, `${message.player_name} left`);
    }
}

function onPlayerReadyChanged(message: Record<string, unknown>): void {
    updateFromServerState(message);
}

function onOwnerChanged(message: Record<string, unknown>): void {
    isOwner = (message.is_owner as boolean) ?? false;
    updateFromServerState(message);
    appendChat(LOG_TYPE_SYSTEM, "You are now the host");
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
        owner_changed: onOwnerChanged,
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

function seatStatusIcon(player: PlayerInfo): string {
    if (player.is_bot) {
        return "\u{1F916}";
    }
    if (player.ready) {
        return "\u2713";
    }
    return "\u25CB";
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
            <div class="room-player-item ${player.is_bot ? "bot" : ""} ${player.is_owner ? "owner" : ""}">
                <span class="room-player-status ${player.ready ? "ready" : "not-ready"}">
                    ${seatStatusIcon(player)}
                </span>
                <span class="room-player-name">${player.name}</span>
                ${
                    player.is_owner
                        ? html`
                              <span class="room-player-badge">Host</span>
                          `
                        : null
                }
            </div>
        `,
        )}
    `,
        container,
    );
}

function updateActionButton(): void {
    const container = document.getElementById("room-action");
    if (!container) {
        return;
    }

    if (isOwner) {
        render(
            html`
            <button class="room-start-btn"
                    ?disabled=${!canStart}
                    @click=${handleStartGame}>
                Start Game
            </button>
        `,
            container,
        );
    } else {
        const myReady = getMyReadyState();
        render(
            html`
            <button class="room-ready-btn ${myReady ? "secondary" : ""}"
                    @click=${handleToggleReady}>
                ${myReady ? "Not Ready" : "Ready"}
            </button>
        `,
            container,
        );
    }
}

function handleToggleReady(): void {
    if (!socket) {
        return;
    }
    const myReady = getMyReadyState();
    socket.send({ ready: !myReady, type: "set_ready" });
}

function handleStartGame(): void {
    if (!socket || !canStart) {
        return;
    }
    socket.send({ type: "start_game" });
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
                    <div id="room-action"></div>
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
    isOwner = false;
    canStart = false;
    currentPlayerName = "";
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
