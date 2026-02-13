import { type RoomInfo, createRoom, listRooms } from "../api";
import { type TemplateResult, html, render } from "lit-html";
import { navigate } from "../router";

const PLAYER_NAME_SUFFIX_LENGTH = 6;

// generates a random player name
function generatePlayerName(): string {
    const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
    let suffix = "";
    for (let idx = 0; idx < PLAYER_NAME_SUFFIX_LENGTH; idx++) {
        suffix += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return `Player_${suffix}`;
}

const playerName = generatePlayerName();

export function lobbyView(): TemplateResult {
    // trigger async load after render
    setTimeout(() => loadAndRenderRooms(), 0);

    return html`
        <div class="lobby">
            <h1>Ronin Mahjong</h1>
            <div class="lobby-controls">
                <button class="btn btn-primary" @click=${handleCreateRoom}>Create Room</button>
                <button class="btn btn-secondary" @click=${() => loadAndRenderRooms()}>Refresh</button>
            </div>
            <div class="lobby-status" id="lobby-status"></div>
            <div class="games-list" id="games-list">Loading rooms...</div>
        </div>
    `;
}

async function loadAndRenderRooms(): Promise<void> {
    const container = document.getElementById("games-list");
    if (!container) {
        return;
    }

    try {
        const rooms = await listRooms();
        if (rooms.length === 0) {
            render(
                html`
                    <p class="empty-message">No rooms available. Create one!</p>
                `,
                container,
            );
        } else {
            render(
                html`
                ${rooms.map(
                    (room) => html`
                    <div class="game-item">
                        <span class="game-id">${room.room_id}</span>
                        <span class="game-players">${room.human_player_count}/${room.humans_needed} players</span>
                        ${renderJoinButton(room)}
                    </div>
                `,
                )}
            `,
                container,
            );
        }
    } catch {
        render(
            html`
                <p class="error-message">Failed to load rooms</p>
            `,
            container,
        );
    }
}

function renderJoinButton(room: RoomInfo): TemplateResult {
    if (room.human_player_count < room.humans_needed) {
        return html`<button class="btn btn-small" @click=${() => joinRoom(room.room_id, room.server_url)}>Join</button>`;
    }
    return html`
        <span class="game-full">Full</span>
    `;
}

function showLobbyStatus(content: TemplateResult): void {
    const statusEl = document.getElementById("lobby-status");
    if (statusEl) {
        render(content, statusEl);
    }
}

async function handleCreateRoom(): Promise<void> {
    showLobbyStatus(
        html`
            <p>Creating room...</p>
        `,
    );
    try {
        const response = await createRoom();
        sessionStorage.setItem("ws_url", response.websocket_url);
        sessionStorage.setItem("player_name", playerName);
        sessionStorage.setItem("room_id", response.room_id);
        navigate(`/room/${response.room_id}`);
    } catch {
        showLobbyStatus(
            html`
                <p class="error-message">Failed to create room</p>
            `,
        );
    }
}

function parseServerUrl(serverUrl: string, roomId: string): URL | undefined {
    try {
        const url = new URL(serverUrl);
        url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
        url.pathname = `/ws/${roomId}`;
        return url;
    } catch {
        return undefined;
    }
}

function joinRoom(roomId: string, serverUrl: string): void {
    const url = parseServerUrl(serverUrl, roomId);
    if (!url) {
        showLobbyStatus(
            html`
                <p class="error-message">Invalid server URL</p>
            `,
        );
        return;
    }
    sessionStorage.setItem("ws_url", url.toString());
    sessionStorage.setItem("player_name", playerName);
    sessionStorage.setItem("room_id", roomId);
    navigate(`/room/${roomId}`);
}
