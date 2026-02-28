import {
    LOG_TYPE_SYSTEM,
    type PlayerInfo,
    type RoomState,
    getMyReadyState,
} from "@/lobby/room/state";
import { html, render } from "lit-html";
import { type ActionCallbacks } from "@/lobby/room/handlers";

function seatStatusIcon(player: PlayerInfo): string {
    if (player.is_bot) {
        return "\u{1F916}";
    }
    if (player.ready) {
        return "\u2713";
    }
    return "\u25CB";
}

function updatePlayerList(state: RoomState): void {
    const container = document.getElementById("room-players");
    if (!container) {
        return;
    }

    render(
        html`
        ${state.players.map(
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

function updateActionButton(state: RoomState, actions: ActionCallbacks): void {
    const container = document.getElementById("room-action");
    if (!container) {
        return;
    }

    if (state.isOwner) {
        render(
            html`
            <button class="room-start-btn"
                    ?disabled=${!state.canStart}
                    @click=${actions.handleStartGame}>
                Start Game
            </button>
        `,
            container,
        );
    } else {
        const myReady = getMyReadyState(state);
        render(
            html`
            <button class="room-ready-btn ${myReady ? "secondary" : ""}"
                    @click=${actions.handleToggleReady}>
                ${myReady ? "Not Ready" : "Ready"}
            </button>
        `,
            container,
        );
    }
}

function updateChatPanel(state: RoomState): void {
    const container = document.getElementById("room-chat-messages");
    if (!container) {
        return;
    }

    render(
        html`
        ${state.chatMessages.map(
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

function updateStatusDisplay(state: RoomState): void {
    const el = document.getElementById("connection-status");
    if (el) {
        el.textContent = state.connectionStatus;
        el.className = `connection-status status-${state.connectionStatus}`;
    }
}

function renderRoomUI(container: HTMLElement, roomId: string, actions: ActionCallbacks): void {
    function handleChatKeydown(event: KeyboardEvent): void {
        if (event.key === "Enter") {
            actions.handleSendChat();
        }
    }

    render(
        html`
        <div class="room">
            <div class="room-header">
                <button class="secondary" @click=${actions.handleLeaveRoom}>Leave Room</button>
                <h2>Room: ${roomId}</h2>
                <span class="connection-status" id="connection-status">disconnected</span>
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
                        <button class="outline" @click=${actions.handleSendChat}>Send</button>
                    </div>
                </div>
            </div>
        </div>
    `,
        container,
    );
}

export { renderRoomUI, updateActionButton, updateChatPanel, updatePlayerList, updateStatusDisplay };
