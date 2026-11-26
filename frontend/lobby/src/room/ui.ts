import { type TemplateResult, html, nothing, render } from "lit-html";

import { chatComposerTemplate, chatLogTemplate, scrollChatToLatest } from "@/chat";
import { type MessageKey, t } from "@/i18n";
import { OCCUPANCY } from "@/occupancy-errors";
import { type ActionCallbacks, describeRoomError } from "@/room/handlers";
import {
    type ConnectionStatus,
    PAGE_ERROR,
    type PageError,
    type PlayerInfo,
    ROOM_SEATS,
    type RoomState,
    canAct,
    describeStartBlocker,
    getMyReadyState,
    isConnectionLost,
    isMe,
    isSeated,
    offersStrongBots,
} from "@/room/state";

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
        <div class="room-player-item ${me ? "me" : ""}">
            <span class="room-player-status ${status.tone}" role="img" title=${status.label} aria-label=${status.label}>
                ${status.glyph}
            </span>
            <span class="room-player-name">${player.name}</span>
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

function openSeatRowTemplate(control: TemplateResult | typeof nothing): TemplateResult {
    const label = t("room.seat.open");
    return html`
        <div class="room-player-item open">
            <span class="room-player-status open" role="img" title=${label} aria-label=${label}></span>
            <span class="room-player-name">${label}</span>
            ${control}
        </div>
    `;
}

function addBotButtonTemplate(state: RoomState, actions: ActionCallbacks): TemplateResult {
    return html`
        <button class="room-seat-btn"
                ?disabled=${!canAct(state)}
                @click=${actions.handleAddStrongBot}>
            ${t("room.seat.add_bot")}
        </button>
    `;
}

function strongBotRowTemplate(state: RoomState, actions: ActionCallbacks): TemplateResult {
    const label = t("room.seat.bot");
    const remove = t("room.seat.remove_bot");
    return html`
        <div class="room-player-item strong-bot">
            <span class="room-player-status" role="img" title=${label} aria-label=${label}></span>
            <span class="room-player-name">${label}</span>
            <button class="room-seat-btn room-seat-remove-btn"
                    title=${remove}
                    aria-label=${remove}
                    ?disabled=${!canAct(state)}
                    @click=${actions.handleRemoveStrongBot}>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                    <path d="M2.5 2.5l7 7M9.5 2.5l-7 7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
            </button>
        </div>
    `;
}

function pendingSeatsTemplate(): TemplateResult {
    return html`
        <div class="room-player-list" aria-busy="true">
            ${Array.from(
                { length: ROOM_SEATS },
                (_seat, index) => html`
                    <div class="room-player-item open">
                        <span class="room-player-status"></span>
                        <span class="room-player-name">${index === 0 ? t("room.taking_seat") : nothing}</span>
                    </div>
                `,
            )}
        </div>
    `;
}

function playerListTemplate(state: RoomState, actions: ActionCallbacks): TemplateResult {
    if (state.players.length === 0) {
        return pendingSeatsTemplate();
    }
    const offered = offersStrongBots(state);
    let openSeat = 0;
    function rowTemplate(player: PlayerInfo): TemplateResult {
        if (!player.is_bot) {
            return playerRowTemplate(state, player);
        }
        openSeat += 1;
        if (!offered) {
            return openSeatRowTemplate(nothing);
        }
        return openSeat <= state.strongBotSeats
            ? strongBotRowTemplate(state, actions)
            : openSeatRowTemplate(addBotButtonTemplate(state, actions));
    }
    return html`
        <div class="room-player-list">${state.players.map(rowTemplate)}</div>
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
        return html`<button class="room-start-btn" disabled>${t("room.start")}</button>`;
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

function panelsTemplate(page: RoomPage): TemplateResult {
    const { actions, state } = page;
    return html`
        <div class="room-content">
            <section class="room-panel room-players-panel" aria-labelledby="room-players-title">
                <h3 class="room-panel-title" id="room-players-title">${t("room.players_title")}</h3>
                ${playerListTemplate(state, actions)}
                <div class="room-action">${actionTemplate(state, actions)}</div>
            </section>
            <section class="room-panel room-chat-panel" aria-labelledby="room-chat-title">
                <h3 class="room-panel-title" id="room-chat-title">${t("room.chat_title")}</h3>
                ${chatLogTemplate(state.chatMessages)}
                ${chatComposerTemplate({
                    chatMaxLength: page.chatMaxLength,
                    enabled: canAct(state),
                    send: actions.handleSendChat,
                })}
            </section>
        </div>
    `;
}

function connectionStatusTemplate(status: ConnectionStatus): TemplateResult {
    return html`
        <span class="connection-status status-${status}" role="status">
            <span class="connection-status-text">
                <span class="connection-status-label">${t(STATUS_LABEL[status])}</span>
                ${Object.values(STATUS_LABEL).map(
                    (key) =>
                        html`<span class="connection-status-sizer" aria-hidden="true">${t(key)}</span>`,
                )}
            </span>
        </span>
    `;
}

function headerTemplate(
    state: RoomState,
    roomName: string,
    actions: ActionCallbacks,
): TemplateResult {
    return html`
        <header class="room-header">
            <h2>${roomName}</h2>
            ${
                state.pageError
                    ? nothing
                    : html`
                          <div class="room-header-actions">
                              ${connectionStatusTemplate(state.connectionStatus)}
                              <button class="outline secondary lobby-small-btn room-leave-btn" @click=${actions.handleLeaveRoom}>${t("room.leave")}</button>
                          </div>
                      `
            }
        </header>
    `;
}

function renderRoom(page: RoomPage): void {
    const { actions, container, roomName, state } = page;
    document.title = t("page.title.with_page", { page: roomName });
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
