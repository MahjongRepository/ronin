import { type TemplateResult, html, nothing, render } from "lit-html";

import { pageFailedView } from "@/app/page-failed";
import { currentGamesTemplate } from "@/current-games";
import { type MessageKey, t, tParts } from "@/i18n";
import { listLoadingTemplate } from "@/list-loading";
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
    readonly returnToGame: () => void;
}

interface ActionsView {
    readonly playing: boolean;
    readonly returning: boolean;
    readonly seated: boolean;
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

function quickMatchTile(): TemplateResult {
    return html`<a href="/matchmaking" class="lobby-action-tile lobby-action-tile--primary">
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
    </a>`;
}

function returnToGameTile(returning: boolean, actions: LobbyActions): TemplateResult {
    return html`<button
        type="button"
        class="lobby-action-tile lobby-action-tile--primary lobby-return-btn"
        ?disabled=${returning}
        aria-busy=${returning ? "true" : "false"}
        @click=${actions.returnToGame}
    >
        <svg class="lobby-action-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M8 5l11 7-11 7z" stroke-linejoin="round" />
        </svg>
        <span class="lobby-action-text">
            <span class="lobby-action-label">${t("lobby.action.return_to_game")}</span>
            <span class="lobby-action-hint">${t("lobby.action.return_to_game_hint")}</span>
        </span>
    </button>`;
}

function actionsTemplate(view: ActionsView, actions: LobbyActions): TemplateResult {
    function submitCreate(event: SubmitEvent): void {
        event.preventDefault();
        actions.createRoom();
    }
    return html`<div class="lobby-actions${view.seated ? " lobby-actions--seated" : ""}">
        ${view.playing ? returnToGameTile(view.returning, actions) : quickMatchTile()}

        <form class="lobby-action-form" @submit=${submitCreate}>
            <button type="submit" class="lobby-action-tile lobby-create-btn" ?disabled=${view.playing}>
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

function joinTemplate(
    room: LobbyRoom,
    isMine: boolean,
    playing: boolean,
): TemplateResult | typeof nothing {
    if (playing) {
        return nothing;
    }
    if (isMine) {
        return html`<a href=${roomPath(room.roomId)} role="button" class="lobby-join-btn"
            >${t("lobby.back_to_table")}</a
        >`;
    }
    if (room.playerCount < ROOM_SEATS) {
        return html`<a href=${roomPath(room.roomId)} role="button" class="lobby-join-btn lobby-join-btn--ghost"
            >${t("lobby.room.join")}</a
        >`;
    }
    return html`<span class="lobby-join-btn lobby-full-badge">${t("lobby.room.full")}</span>`;
}

function roomRow(room: LobbyRoom, myRoomId: string | null, playing: boolean): TemplateResult {
    const isMine = room.roomId === myRoomId;
    return html`<li class="lobby-room-row${isMine ? " lobby-room-row--mine" : ""}">
        <span class="lobby-table-name">${room.name}</span>
        ${seatNamesTemplate(room.players.map((player) => (player.isBot ? null : player.name)))}
        ${joinTemplate(room, isMine, playing)}
    </li>`;
}

function emptyTablesHint(actions: LobbyActions): TemplateResult {
    const host = html`<button type="button" class="lobby-link-btn" @click=${actions.createRoom}>
        ${t("lobby.tables.empty_host")}
    </button>`;
    const quickMatch = html`<a href="/matchmaking">${t("lobby.tables.empty_quick_match")}</a>`;
    return html`<p class="lobby-empty-hint">
        ${tParts("lobby.tables.empty_hint", { host, quick_match: quickMatch })}
    </p>`;
}

function roomsListTemplate(
    rooms: LobbyRooms,
    playing: boolean,
    actions: LobbyActions,
): TemplateResult {
    return rooms.rooms.length > 0
        ? html`<ul class="lobby-room-list">
                  ${rooms.rooms.map((room) => roomRow(room, rooms.myRoomId, playing))}
              </ul>`
        : html`<div class="lobby-empty lobby-empty--boxed">
                  <p class="lobby-empty-title">${t("lobby.tables.empty_title")}</p>
                  ${playing ? nothing : emptyTablesHint(actions)}
              </div>`;
}

function tablesTemplate(
    rooms: LobbyRooms | null,
    playing: boolean,
    actions: LobbyActions,
): TemplateResult {
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

        ${rooms ? roomsListTemplate(rooms, playing, actions) : listLoadingTemplate("rows", 3)}
    </section>`;
}

function lobbyTemplate(state: LobbyState, actions: LobbyActions): TemplateResult {
    if (state.loadFailed) {
        return pageFailedView();
    }
    const seated = state.rooms && !state.liveGame.playing ? seatedTable(state.rooms) : null;
    return html`${state.notice ? alertTemplate("warning", state.notice) : nothing}
        ${state.createFailed ? alertTemplate("error", "lobby.error.create_failed") : nothing}
        ${state.liveGame.returnFailed ? alertTemplate("error", "common.return_failed") : nothing}
        ${seated ? seatedHint(seated) : nothing}
        ${actionsTemplate(
            {
                playing: state.liveGame.playing,
                returning: state.liveGame.returning,
                seated: seated !== null,
            },
            actions,
        )}
        ${tablesTemplate(state.rooms, state.liveGame.playing, actions)}
        ${currentGamesTemplate(state.games, "lobby-games-title")}`;
}

export function renderLobby(host: HTMLElement, state: LobbyState, actions: LobbyActions): void {
    document.title = t("page.title.default");
    render(lobbyTemplate(state, actions), host);
}
