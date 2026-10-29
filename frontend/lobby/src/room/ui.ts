import { type TemplateResult, html, nothing, render } from "lit-html";

import { type MessageKey, t } from "@/i18n";
import { OCCUPANCY } from "@/occupancy-errors";
import { type ActionCallbacks, describeRoomError } from "@/room/handlers";
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

const IME_PROCESS_KEY_CODE = 229;

const STATUS_LABEL: Readonly<Record<ConnectionStatus, MessageKey>> = {
    connected: "room.status.connected",
    connecting: "room.status.connecting",
    disconnected: "room.status.disconnected",
    error: "room.status.error",
};

interface RoomPage {
    actions: ActionCallbacks;
    chatMaxLength: number;
    container: HTMLElement;
    roomName: string;
    state: RoomState;
}

interface RecoveryLink {
    href: string;
    label: string;
}

function backToLobbyLink(): RecoveryLink {
    return { href: "/", label: t("common.back_to_lobby") };
}

function reloadLink(): RecoveryLink {
    return { href: window.location.pathname, label: t("common.reload") };
}

function recoveryLinks({ code, seatedRoomId }: PageError): RecoveryLink[] {
    if (code === OCCUPANCY.ALREADY_IN_ROOM && seatedRoomId) {
        return [
            { href: `/rooms/${encodeURIComponent(seatedRoomId)}`, label: t("common.go_to_table") },
            backToLobbyLink(),
        ];
    }
    switch (code) {
        case OCCUPANCY.ALREADY_IN_QUEUE: {
            return [
                { href: "/matchmaking", label: t("common.go_to_matchmaking") },
                backToLobbyLink(),
            ];
        }
        case PAGE_ERROR.GAME_START_INVALID:
        case PAGE_ERROR.JOIN_RETRIES_EXHAUSTED:
        case PAGE_ERROR.PAGE_SETUP_FAILED: {
            return [reloadLink(), backToLobbyLink()];
        }
        default: {
            return [backToLobbyLink()];
        }
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
        return alertTemplate(
            "error",
            describeRoomError(state.pageError.code),
            recoveryLinks(state.pageError),
        );
    }
    if (isConnectionLost(state)) {
        return alertTemplate("warning", t("room.connection_lost"), [
            reloadLink(),
            backToLobbyLink(),
        ]);
    }
    return nothing;
}

function seatStatus(player: PlayerInfo): { glyph: string; label: string; tone: string } {
    if (player.is_bot) {
        return { glyph: "", label: t("room.seat.open"), tone: "open" };
    }
    if (player.is_owner) {
        return { glyph: "", label: t("room.seat.host"), tone: "host" };
    }
    if (player.ready) {
        return { glyph: "✓", label: t("room.seat.ready"), tone: "ready" };
    }
    return { glyph: "○", label: t("room.seat.not_ready"), tone: "not-ready" };
}

function seatBadge(player: PlayerInfo): TemplateResult | typeof nothing {
    if (player.is_owner) {
        return html`
            <span class="room-player-badge">${t("room.seat.host")}</span>
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
            <span class="room-player-name">${player.is_bot ? t("room.seat.open") : player.name}</span>
            ${
                me
                    ? html`
                          <span class="room-player-badge you">${t("room.badge.you")}</span>
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
            <p class="room-placeholder">${t("room.taking_seat")}</p>
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
                ${t("room.start")}
            </button>
            ${actionHintTemplate(blocker)}
        `;
    }
    const ready = getMyReadyState(state);
    const hint = ready ? t("room.hint.ready") : t("room.hint.not_ready");
    return html`
        <button class="room-ready-btn ${ready ? "outline secondary" : ""}"
                ?disabled=${!enabled}
                aria-describedby=${enabled ? "room-action-hint" : nothing}
                @click=${actions.handleToggleReady}>
            ${ready ? t("room.cancel_ready") : t("room.ready")}
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
                   aria-label=${t("room.chat.label")}
                   autocomplete="off"
                   maxlength=${chatMaxLength}
                   placeholder=${t("room.chat.placeholder")}
                   ?disabled=${!enabled}
                   @keydown=${blockImeEnter} />
            <button type="submit" class="outline" ?disabled=${!enabled}>${t("room.chat.send")}</button>
        </form>
    `;
}

function panelsTemplate(page: RoomPage): TemplateResult {
    const { actions, state } = page;
    return html`
        <div class="room-content">
            <section class="room-panel room-players-panel" aria-labelledby="room-players-title">
                <h3 class="room-panel-title" id="room-players-title">${t("room.players_title")}</h3>
                ${playerListTemplate(state)}
                <div class="room-action">${actionTemplate(state, actions)}</div>
            </section>
            <section class="room-panel room-chat-panel" aria-labelledby="room-chat-title">
                <h3 class="room-panel-title" id="room-chat-title">${t("room.chat_title")}</h3>
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
    roomName: string,
    actions: ActionCallbacks,
): TemplateResult {
    const status = state.connectionStatus;
    return html`
        <header class="room-header">
            <h2>${roomName}</h2>
            <div class="room-header-actions">
                ${
                    state.pageError
                        ? nothing
                        : html`<span class="connection-status status-${status}" role="status">${t(STATUS_LABEL[status])}</span>`
                }
                ${
                    isSeated(state)
                        ? html`<button class="outline secondary lobby-small-btn room-leave-btn" @click=${actions.handleLeaveRoom}>${t("room.leave")}</button>`
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
    const { actions, container, roomName, state } = page;
    render(
        html`
            <div class="room">
                ${headerTemplate(state, roomName, actions)}
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
