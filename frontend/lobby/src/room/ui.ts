import { type TemplateResult, html, nothing, render } from "lit-html";

import { OCCUPANCY } from "@/occupancy-errors";
import { type ActionCallbacks } from "@/room/handlers";
import {
    type ChatEntry,
    type ConnectionStatus,
    LOG_TYPE_SYSTEM,
    PAGE_ERROR,
    type PageError,
    type PlayerInfo,
    type RoomState,
    canAct,
    describeStartBlocker,
    getMyReadyState,
    isConnectionLost,
    isMe,
    isSeated,
} from "@/room/state";

const SHORT_ROOM_ID_LENGTH = 8;
const IME_PROCESS_KEY_CODE = 229;
const OPEN_SEAT = "Open seat";
const CONNECTION_LOST_TEXT = "The connection to the table was lost. Reload the page to rejoin.";

const STATUS_LABEL: Readonly<Record<ConnectionStatus, string>> = {
    connected: "Connected",
    connecting: "Connecting…",
    disconnected: "Disconnected",
    error: "Connection error",
};

interface RoomPage {
    actions: ActionCallbacks;
    chatMaxLength: number;
    container: HTMLElement;
    roomId: string;
    state: RoomState;
}

interface RecoveryLink {
    href: string;
    label: string;
}

function backToLobbyLink(): RecoveryLink {
    return { href: "/", label: "Back to lobby" };
}

function reloadLink(): RecoveryLink {
    return { href: window.location.pathname, label: "Reload" };
}

function recoveryLinks({ code, seatedRoomId }: PageError): RecoveryLink[] {
    if (code === OCCUPANCY.ALREADY_IN_ROOM && seatedRoomId) {
        return [
            { href: `/rooms/${encodeURIComponent(seatedRoomId)}`, label: "Go to your table" },
            backToLobbyLink(),
        ];
    }
    switch (code) {
        case OCCUPANCY.ALREADY_IN_QUEUE:
            return [{ href: "/matchmaking", label: "Go to matchmaking" }, backToLobbyLink()];
        case PAGE_ERROR.GAME_START_INVALID:
        case PAGE_ERROR.JOIN_RETRIES_EXHAUSTED:
        case PAGE_ERROR.PAGE_SETUP_FAILED:
            return [reloadLink(), backToLobbyLink()];
        default:
            return [backToLobbyLink()];
    }
}

function alertTemplate(
    tone: "error" | "warning",
    text: string,
    links: readonly RecoveryLink[],
): TemplateResult {
    return html`
        <div class="lobby-alert ${tone === "warning" ? "warning" : ""}" role="alert">
            <p>${text}</p>
            <p class="lobby-alert-actions">
                ${links.map((link) => html`<a href=${link.href}>${link.label}</a>`)}
            </p>
        </div>
    `;
}

function noticeTemplate(state: RoomState): TemplateResult | typeof nothing {
    if (state.pageError) {
        return alertTemplate("error", state.pageError.text, recoveryLinks(state.pageError));
    }
    if (isConnectionLost(state)) {
        return alertTemplate("warning", CONNECTION_LOST_TEXT, [reloadLink(), backToLobbyLink()]);
    }
    return nothing;
}

function seatStatus(player: PlayerInfo): { glyph: string; label: string; tone: string } {
    if (player.is_bot) {
        return { glyph: "", label: OPEN_SEAT, tone: "open" };
    }
    if (player.is_owner) {
        return { glyph: "", label: "Host", tone: "host" };
    }
    if (player.ready) {
        return { glyph: "✓", label: "Ready", tone: "ready" };
    }
    return { glyph: "○", label: "Not ready", tone: "not-ready" };
}

function seatBadge(player: PlayerInfo): TemplateResult | typeof nothing {
    if (player.is_owner) {
        return html`
            <span class="room-player-badge">Host</span>
        `;
    }
    return nothing;
}

function playerRowTemplate(state: RoomState, player: PlayerInfo): TemplateResult {
    const status = seatStatus(player);
    const me = isMe(state, player);
    return html`
        <div class="room-player-item ${player.is_bot ? "open" : ""} ${me ? "me" : ""}">
            <span class="room-player-status ${status.tone}" role="img" title=${status.label} aria-label=${status.label}>
                ${status.glyph}
            </span>
            <span class="room-player-name">${player.is_bot ? OPEN_SEAT : player.name}</span>
            ${
                me
                    ? html`
                          <span class="room-player-badge you">You</span>
                      `
                    : nothing
            }
            ${seatBadge(player)}
        </div>
    `;
}

function playerListTemplate(state: RoomState): TemplateResult {
    if (state.players.length === 0) {
        return html`
            <p class="room-placeholder">Taking a seat…</p>
        `;
    }
    return html`
        <div class="room-player-list">
            ${state.players.map((player) => playerRowTemplate(state, player))}
        </div>
    `;
}

function actionHintTemplate(hint: string | null): TemplateResult | typeof nothing {
    if (hint === null) {
        return nothing;
    }
    return html`<p class="room-action-hint" id="room-action-hint">${hint}</p>`;
}

function actionTemplate(
    state: RoomState,
    actions: ActionCallbacks,
): TemplateResult | typeof nothing {
    if (!isSeated(state)) {
        return nothing;
    }
    const enabled = canAct(state);
    if (state.isOwner) {
        const blocker = enabled ? describeStartBlocker(state) : null;
        return html`
            <button class="room-start-btn"
                    ?disabled=${!enabled || !state.canStart}
                    aria-describedby=${blocker ? "room-action-hint" : nothing}
                    @click=${actions.handleStartGame}>
                Start game
            </button>
            ${actionHintTemplate(blocker)}
        `;
    }
    const ready = getMyReadyState(state);
    const hint = ready
        ? "You're ready. Waiting for the host to start."
        : "The host can start once you're ready.";
    return html`
        <button class="room-ready-btn ${ready ? "outline secondary" : ""}"
                ?disabled=${!enabled}
                aria-describedby=${enabled ? "room-action-hint" : nothing}
                @click=${actions.handleToggleReady}>
            ${ready ? "Cancel ready" : "Ready"}
        </button>
        ${actionHintTemplate(enabled ? hint : null)}
    `;
}

function chatEntryTemplate(entry: ChatEntry): TemplateResult {
    const system = entry.sender === LOG_TYPE_SYSTEM;
    return html`
        <div class="room-chat-entry ${system ? "system" : ""}">
            <span class="room-chat-time">${entry.timestamp}</span>
            ${system ? nothing : html`<span class="room-chat-sender">${entry.sender}</span>`}
            <span class="room-chat-text">${entry.text}</span>
        </div>
    `;
}

function blockImeEnter(event: KeyboardEvent): void {
    const composing = event.isComposing || event.keyCode === IME_PROCESS_KEY_CODE;
    if (event.key === "Enter" && composing) {
        event.preventDefault();
    }
}

function chatComposerTemplate(page: RoomPage): TemplateResult {
    const { actions, chatMaxLength, state } = page;
    function handleSubmit(event: SubmitEvent): void {
        event.preventDefault();
        const form = event.currentTarget;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }
        const input = form.elements.namedItem("text");
        if (!(input instanceof HTMLInputElement)) {
            return;
        }
        if (actions.handleSendChat(input.value)) {
            input.value = "";
        }
    }

    const enabled = canAct(state);
    return html`
        <form class="room-chat-input" role="group" @submit=${handleSubmit}>
            <input type="text"
                   id="chat-input"
                   name="text"
                   aria-label="Chat message"
                   autocomplete="off"
                   maxlength=${chatMaxLength}
                   placeholder="Type a message…"
                   ?disabled=${!enabled}
                   @keydown=${blockImeEnter} />
            <button type="submit" class="outline" ?disabled=${!enabled}>Send</button>
        </form>
    `;
}

function panelsTemplate(page: RoomPage): TemplateResult {
    const { actions, state } = page;
    return html`
        <div class="room-content">
            <section class="room-panel room-players-panel" aria-labelledby="room-players-title">
                <h3 class="room-panel-title" id="room-players-title">Players</h3>
                ${playerListTemplate(state)}
                <div class="room-action">${actionTemplate(state, actions)}</div>
            </section>
            <section class="room-panel room-chat-panel" aria-labelledby="room-chat-title">
                <h3 class="room-panel-title" id="room-chat-title">Chat</h3>
                <div class="room-chat-messages" id="room-chat-messages" role="log" aria-live="polite">
                    ${state.chatMessages.map(chatEntryTemplate)}
                </div>
                ${chatComposerTemplate(page)}
            </section>
        </div>
    `;
}

function headerTemplate(
    state: RoomState,
    roomId: string,
    actions: ActionCallbacks,
): TemplateResult {
    const status = state.connectionStatus;
    return html`
        <header class="room-header">
            <h2 title=${roomId}>Table <code class="lobby-room-id">${roomId.slice(0, SHORT_ROOM_ID_LENGTH)}</code></h2>
            <div class="room-header-actions">
                ${
                    state.pageError
                        ? nothing
                        : html`<span class="connection-status status-${status}" role="status">${STATUS_LABEL[status]}</span>`
                }
                ${
                    isSeated(state)
                        ? html`<button class="outline secondary lobby-small-btn room-leave-btn" @click=${actions.handleLeaveRoom}>Leave table</button>`
                        : nothing
                }
            </div>
        </header>
    `;
}

function scrollChatToLatest(container: HTMLElement, count: number): void {
    const log = container.querySelector<HTMLElement>("#room-chat-messages");
    if (!log || log.dataset.count === String(count)) {
        return;
    }
    log.dataset.count = String(count);
    log.scrollTop = log.scrollHeight;
}

function renderRoom(page: RoomPage): void {
    const { actions, container, roomId, state } = page;
    render(
        html`
            <div class="room">
                ${headerTemplate(state, roomId, actions)}
                ${noticeTemplate(state)}
                ${state.pageError ? nothing : panelsTemplate(page)}
            </div>
        `,
        container,
    );
    scrollChatToLatest(container, state.chatMessages.length);
}

export { renderRoom };
export type { RoomPage };
