import { type TemplateResult, html, nothing, render } from "lit-html";

import { type MessageKey, t } from "@/i18n";
import {
    type EndingCode,
    GAME_START_INVALID,
    MATCHMAKING_SEATS,
    MATCH_FAILED,
    type MatchmakingEnd,
    type MatchmakingState,
    canRetry,
} from "@/matchmaking/state";
import { OCCUPANCY, OCCUPANCY_TEXT, isOccupancyCode } from "@/occupancy-errors";

interface MatchmakingActions {
    onRetry: () => void;
}

interface EndingCopy {
    text: MessageKey;
    title: MessageKey;
}

const STOPPED = "matchmaking.title.stopped";

const ENDING_TITLE: Readonly<Record<EndingCode, MessageKey>> = {
    [GAME_START_INVALID]: STOPPED,
    [MATCH_FAILED]: "matchmaking.title.match_failed",
    [OCCUPANCY.ALREADY_IN_GAME]: STOPPED,
    [OCCUPANCY.ALREADY_IN_ROOM]: STOPPED,
    [OCCUPANCY.MATCH_STARTING]: STOPPED,
    [OCCUPANCY.REPLACED_BY_NEW_CONNECTION]: "matchmaking.title.replaced",
};

const MATCHMAKING_ERROR_TEXT = {
    [GAME_START_INVALID]: "matchmaking.error.game_start_invalid",
    [MATCH_FAILED]: "matchmaking.error.match_failed",
} as const satisfies Readonly<Record<string, MessageKey>>;

const CONNECTION_LOST: EndingCopy = {
    text: "matchmaking.connection_lost",
    title: STOPPED,
};

function endingCopy(code: EndingCode): EndingCopy {
    const text = isOccupancyCode(code) ? OCCUPANCY_TEXT[code] : MATCHMAKING_ERROR_TEXT[code];
    return { text, title: ENDING_TITLE[code] };
}

function seatsTemplate(filled: number): TemplateResult {
    const seats = Array.from({ length: MATCHMAKING_SEATS }, (_seat, index) => index < filled);
    return html`
        <div class="lobby-table-vis matchmaking-seats" aria-hidden="true">
            ${seats.map(
                (isFilled) =>
                    html`<span class="lobby-seat ${isFilled ? "filled" : "waiting"}"></span>`,
            )}
        </div>
    `;
}

function searchingStatus(state: MatchmakingState): string {
    if (state.phase === "starting") {
        return t("matchmaking.status.starting");
    }
    if (state.phase === "searching") {
        return t("matchmaking.status.found", { count: state.queueSize, total: MATCHMAKING_SEATS });
    }
    return t("matchmaking.status.looking");
}

function searchingTemplate(state: MatchmakingState): TemplateResult {
    const found = state.phase === "starting" ? MATCHMAKING_SEATS : state.queueSize;
    const status = searchingStatus(state);
    return html`
        <h2>${state.phase === "starting" ? t("matchmaking.title.found") : t("matchmaking.title.finding")}</h2>
        ${seatsTemplate(found)}
        <p class="matchmaking-status" role="status" aria-live="polite">${status}</p>
        <p class="matchmaking-hint lobby-muted">${t("matchmaking.hint", { count: MATCHMAKING_SEATS })}</p>
        <div class="lobby-button-row lobby-button-row--center matchmaking-actions">
            ${
                state.phase === "starting"
                    ? nothing
                    : html`
                          <a href="/" role="button" class="secondary outline">${t("matchmaking.cancel")}</a>
                      `
            }
        </div>
    `;
}

function tableLinkTemplate(end: MatchmakingEnd): TemplateResult | typeof nothing {
    if (end.code !== OCCUPANCY.ALREADY_IN_ROOM || !end.seatedRoomId) {
        return nothing;
    }
    return html`<a href="/rooms/${encodeURIComponent(end.seatedRoomId)}" role="button">${t("common.go_to_table")}</a>`;
}

function endedTemplate(state: MatchmakingState, actions: MatchmakingActions): TemplateResult {
    const { end } = state;
    const copy = end ? endingCopy(end.code) : CONNECTION_LOST;
    const retry = canRetry(state);
    return html`
        <h2>${t(copy.title)}</h2>
        <div class="lobby-alert ${end?.code === OCCUPANCY.REPLACED_BY_NEW_CONNECTION ? "warning" : ""}" role="alert">
            <p>${t(copy.text)}</p>
        </div>
        <div class="lobby-button-row lobby-button-row--center matchmaking-actions">
            ${end ? tableLinkTemplate(end) : nothing}
            ${
                retry
                    ? html`<button type="button" class="matchmaking-retry" @click=${actions.onRetry}>
                      ${t("matchmaking.search_again")}
                  </button>`
                    : nothing
            }
            <a href="/" role="button" class="secondary outline">${t("common.back_to_lobby")}</a>
        </div>
    `;
}

function matchmakingTemplate(state: MatchmakingState, actions: MatchmakingActions): TemplateResult {
    const ended = state.phase === "ended" || state.phase === "disconnected";
    return html`
        <div class="matchmaking-card" data-phase=${state.phase} aria-busy=${state.phase === "connecting"}>
            ${ended ? endedTemplate(state, actions) : searchingTemplate(state)}
        </div>
    `;
}

function renderMatchmaking(
    container: HTMLElement,
    state: MatchmakingState,
    actions: MatchmakingActions,
): void {
    render(matchmakingTemplate(state, actions), container);
}

export { renderMatchmaking };
export type { MatchmakingActions };
