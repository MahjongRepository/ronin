import {
    ClientMessageType,
    ConnectionStatus,
    LOG_TYPE_SYSTEM,
    LOG_TYPE_UNKNOWN,
    type RoomPlayerInfo,
    SessionMessageType,
} from "../protocol";
import { type TemplateResult, html, render } from "lit-html";
import { beginHandoff, isHandoffPending, setActiveSocket } from "../socket-handoff";
import { clearSessionData, getSessionToken, setSessionToken } from "../session-storage";
import { GameSocket } from "../websocket";
import { navigate } from "../router";

interface ChatEntry {
    sender: string;
    text: string;
    timestamp: string;
}

let socket: GameSocket | null = null;
let players: RoomPlayerInfo[] = [];
let chatMessages: ChatEntry[] = [];
let connectionStatus = ConnectionStatus.DISCONNECTED;
let currentRoomId = "";
let isReady = false;
let messageHandlers: Record<string, (msg: Record<string, unknown>) => void> = {};
// incremented on each roomView call, checked in deferred connectToRoom
// to prevent orphaned connections after rapid navigation
let viewGeneration = 0;

function resetRoomState(roomId: string): void {
    players = [];
    chatMessages = [];
    connectionStatus = ConnectionStatus.DISCONNECTED;
    currentRoomId = roomId;
    isReady = false;
}

export function roomView(roomId: string): TemplateResult {
    const wsUrl = sessionStorage.getItem("ws_url");
    const playerName = sessionStorage.getItem("player_name");

    if (!wsUrl || !playerName || !wsUrl.includes(`/ws/${roomId}`)) {
        return redirectToLobby();
    }

    resetRoomState(roomId);
    const generation = ++viewGeneration;

    // connect after render; bail if navigation happened before timeout fires
    setTimeout(() => {
        if (viewGeneration !== generation) {
            return;
        }
        connectToRoom(wsUrl, roomId, playerName);
    }, 0);

    return renderRoomView(roomId);
}

function redirectToLobby(): TemplateResult {
    clearSessionData();
    setTimeout(() => navigate("/"), 0);
    return html`
        <p>Redirecting to lobby...</p>
    `;
}

function connectToRoom(wsUrl: string, roomId: string, playerName: string): void {
    if (socket) {
        socket.disconnect();
    }

    messageHandlers = buildMessageHandlers(roomId);

    socket = new GameSocket(
        (message) => handleRoomMessage(message),
        (status) => {
            connectionStatus = status;
            updateStatusDisplay();

            // send join_room when connected
            if (status === ConnectionStatus.CONNECTED && socket) {
                socket.send({
                    player_name: playerName,
                    room_id: roomId,
                    session_token: getSessionToken(),
                    type: ClientMessageType.JOIN_ROOM,
                });
            }
        },
    );

    setActiveSocket(socket);
    socket.connect(wsUrl);
}

function onRoomJoined(message: Record<string, unknown>): void {
    if (message.session_token) {
        setSessionToken(message.session_token as string);
    }
    players = (message.players as RoomPlayerInfo[]) ?? [];
    updatePlayerList();
    appendChat(LOG_TYPE_SYSTEM, "Joined room");
}

function onPlayerJoined(message: Record<string, unknown>): void {
    players.push({ name: message.player_name as string, ready: false });
    updatePlayerList();
    appendChat(LOG_TYPE_SYSTEM, `${message.player_name} joined`);
}

function onPlayerLeft(message: Record<string, unknown>): void {
    players = players.filter((pl) => pl.name !== (message.player_name as string));
    updatePlayerList();
    appendChat(LOG_TYPE_SYSTEM, `${message.player_name} left`);
}

function onPlayerReadyChanged(message: Record<string, unknown>): void {
    const player = players.find((pl) => pl.name === (message.player_name as string));
    if (player) {
        player.ready = message.ready as boolean;
    }
    updatePlayerList();
    appendChat(
        LOG_TYPE_SYSTEM,
        `${message.player_name} is ${message.ready ? "ready" : "not ready"}`,
    );
}

function onGameStarting(roomId: string): void {
    appendChat(LOG_TYPE_SYSTEM, "Game starting!");
    beginHandoff(roomId);
    navigate(`/game/${roomId}`);
}

function buildMessageHandlers(
    roomId: string,
): Record<string, (msg: Record<string, unknown>) => void> {
    return {
        [SessionMessageType.ROOM_JOINED]: onRoomJoined,
        [SessionMessageType.PLAYER_JOINED]: onPlayerJoined,
        [SessionMessageType.PLAYER_LEFT]: onPlayerLeft,
        [SessionMessageType.PLAYER_READY_CHANGED]: onPlayerReadyChanged,
        [SessionMessageType.GAME_STARTING]: () => onGameStarting(roomId),
        [SessionMessageType.CHAT]: (msg) =>
            appendChat(msg.player_name as string, msg.text as string),
        [SessionMessageType.ERROR]: (msg) => appendChat(LOG_TYPE_SYSTEM, `Error: ${msg.message}`),
        [SessionMessageType.PONG]: () => {},
    };
}

function handleRoomMessage(message: Record<string, unknown>): void {
    const handler = messageHandlers[message.type as string];
    if (handler) {
        handler(message);
    } else {
        appendChat(LOG_TYPE_UNKNOWN, JSON.stringify(message, null, 2));
    }
}

function appendChat(sender: string, text: string): void {
    chatMessages.push({
        sender,
        text,
        timestamp: new Date().toLocaleTimeString(),
    });
    updateChatPanel();
}

function renderRoomView(roomId: string): TemplateResult {
    return html`
        <div class="room">
            <div class="room-header">
                <button class="btn btn-secondary" @click=${handleLeaveRoom}>Leave Room</button>
                <h2>Room: ${roomId}</h2>
                <span class="connection-status" id="connection-status">${connectionStatus}</span>
            </div>
            <div class="room-content">
                <div class="room-players-panel">
                    <h3>Players</h3>
                    <div id="room-players"></div>
                    <button class="btn btn-primary room-ready-btn" id="ready-btn" @click=${handleToggleReady}>
                        Ready
                    </button>
                </div>
                <div class="room-chat-panel">
                    <h3>Chat</h3>
                    <div class="room-chat-messages" id="room-chat-messages"></div>
                    <div class="room-chat-input">
                        <input type="text" id="chat-input" placeholder="Type a message..." @keydown=${handleChatKeydown} />
                        <button class="btn btn-small" @click=${handleSendChat}>Send</button>
                    </div>
                </div>
            </div>
        </div>
    `;
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

    // auto-scroll to bottom
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
    socket.send({
        ready: isReady,
        type: ClientMessageType.SET_READY,
    });

    // update button text
    const btn = document.getElementById("ready-btn");
    if (btn) {
        btn.textContent = isReady ? "Not Ready" : "Ready";
        btn.className = `btn room-ready-btn ${isReady ? "btn-secondary" : "btn-primary"}`;
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
    socket.send({
        text,
        type: ClientMessageType.CHAT,
    });
    input.value = "";
}

function handleLeaveRoom(): void {
    if (socket) {
        socket.send({ type: ClientMessageType.LEAVE_ROOM });
    }
    clearSessionData();
    // router calls cleanupRoomView via route cleanup on navigation
    navigate("/");
}

export function cleanupRoomView(): void {
    viewGeneration++;
    // during handoff, socket ownership moves to socket-handoff module
    // only disconnect if no handoff is pending
    if (socket) {
        if (!isHandoffPending(currentRoomId)) {
            socket.disconnect();
        }
        socket = null;
    }
    players = [];
    chatMessages = [];
}
