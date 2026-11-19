import { type TemplateResult, html, nothing, render } from "lit-html";

import { pageFailedView } from "@/app/page-failed";
import { currentGamesTemplate } from "@/current-games";
import { type MessageKey, t, tParts } from "@/i18n";
import {
    type LobbyRoom,
    type LobbyRooms,
    type LobbyState,
    type SeatedTable,
    roomPath,
    seatedTable,
} from "@/lobby/state";
import { ROOM_SEATS } from "@/room/state";
import { seatNamesTemplate } from "@/seat-names";

export interface LobbyActions {
    readonly createRoom: () => void;
}

function alertTemplate(tone: "error" | "warning", key: MessageKey): TemplateResult {
    return html`<div class="lobby-alert ${tone === "warning" ? "warning" : ""}" role="alert">
        <p>${t(key)}</p>
    </div>`;
}

function seatedHint(room: SeatedTable): TemplateResult {
    const name = room.name ?? t("room.fallback_name");
    const table = html`<strong class="lobby-table-name">${name}</strong>`;
    return html`<p class="lobby-seated-hint">
        ${tParts("lobby.seated_hint", { table })}
        <a href=${roomPath(room.roomId)}>${t("lobby.back_to_table")}</a>
    </p>`;
}

function actionsTemplate(seated: boolean, actions: LobbyActions): TemplateResult {
    function submitCreate(event: SubmitEvent): void {
        event.preventDefault();
        actions.createRoom();
    }
    return html`<div class="lobby-actions${seated ? " lobby-actions--seated" : ""}">
        <a href="/matchmaking" class="lobby-action-tile lobby-action-tile--primary">
            <svg class="lobby-action-icon" viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="5" r="2.25" />
                <circle cx="19" cy="12" r="2.25" />
                <circle cx="12" cy="19" r="2.25" />
                <circle cx="5" cy="12" r="2.25" />
            </svg>
            <span class="lobby-action-text">
                <span class="lobby-action-label">${t("lobby.action.quick_match")}</span>
                <span class="lobby-action-hint">${t("lobby.action.quick_match_hint")}</span>
            </span>
        </a>

        <form class="lobby-action-form" @submit=${submitCreate}>
            <button type="submit" class="lobby-action-tile lobby-create-btn">
                <svg class="lobby-action-icon" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 5v14M5 12h14" />
                </svg>
                <span class="lobby-action-text">
                    <span class="lobby-action-label">${t("lobby.action.custom_table")}</span>
                    <span class="lobby-action-hint">${t("lobby.action.custom_table_hint")}</span>
                </span>
            </button>
        </form>
    </div>`;
}

function joinTemplate(room: LobbyRoom, isMine: boolean): TemplateResult {
    if (isMine) {
        return html`<a href=${roomPath(room.roomId)} role="button" class="lobby-join-btn"
            >${t("lobby.back_to_table")}</a
        >`;
    }
    if (room.playerCount < ROOM_SEATS) {
        return html`<a href=${roomPath(room.roomId)} role="button" class="outline lobby-join-btn"
            >${t("lobby.room.join")}</a
        >`;
    }
    return html`<span class="lobby-join-btn lobby-full-badge">${t("lobby.room.full")}</span>`;
}

function roomRow(room: LobbyRoom, myRoomId: string | null): TemplateResult {
    const isMine = room.roomId === myRoomId;
    return html`<li class="lobby-room-row${isMine ? " lobby-room-row--mine" : ""}">
        <span class="lobby-table-name">${room.name}</span>
        ${seatNamesTemplate(room.players.map((player) => (player.isBot ? null : player.name)))}
        ${joinTemplate(room, isMine)}
    </li>`;
}

function roomsListTemplate(rooms: LobbyRooms): TemplateResult {
    return rooms.rooms.length > 0
        ? html`<ul class="lobby-room-list">
                  ${rooms.rooms.map((room) => roomRow(room, rooms.myRoomId))}
              </ul>`
        : html`<div class="lobby-empty lobby-empty--boxed">
                  <p class="lobby-empty-title">${t("lobby.tables.empty_title")}</p>
                  <p class="lobby-empty-hint">${t("lobby.tables.empty_hint")}</p>
              </div>`;
}

function tablesTemplate(rooms: LobbyRooms | null): TemplateResult {
    return html`<section class="lobby-section">
        <div class="lobby-section-header">
            <h2>${t("lobby.tables.title")}</h2>
            ${
                rooms && rooms.rooms.length > 0
                    ? html`<small class="lobby-table-count"
                      >${t("lobby.tables.open_count", { count: rooms.rooms.length })}</small
                  >`
                    : nothing
            }
        </div>

        ${rooms ? roomsListTemplate(rooms) : nothing}
    </section>`;
}

function lobbyTemplate(state: LobbyState, actions: LobbyActions): TemplateResult {
    if (state.loadFailed) {
        return pageFailedView();
    }
    const seated = state.rooms ? seatedTable(state.rooms) : null;
    return html`${state.notice ? alertTemplate("warning", state.notice) : nothing}
        ${state.createFailed ? alertTemplate("error", "lobby.error.create_failed") : nothing}
        ${seated ? seatedHint(seated) : nothing}
        ${actionsTemplate(seated !== null, actions)} ${tablesTemplate(state.rooms)}
        ${currentGamesTemplate(state.games, "lobby-games-title")}`;
}

export function renderLobby(host: HTMLElement, state: LobbyState, actions: LobbyActions): void {
    document.title = t("page.title.default");
    render(lobbyTemplate(state, actions), host);
}
