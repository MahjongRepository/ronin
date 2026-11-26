import { type TemplateResult, html, nothing, render } from "lit-html";

import {
    type ChatEntry,
    LOG_TYPE_SYSTEM,
    chatComposerTemplate,
    chatLogTemplate,
    scrollChatToLatest,
} from "@/chat";
import { currentGameRowsTemplate } from "@/current-games";
import { type MessageKey, formatDate, formatList, t } from "@/i18n";
import { listLoadingTemplate } from "@/list-loading";
import { describeTournamentError } from "@/tournament/handlers";
import { playedGamesTemplate } from "@/tournament/played-games";
import {
    PAGE_ERROR,
    TOURNAMENT_TABS,
    type TournamentConfig,
    type TournamentState,
    type TournamentTab,
    isConnectionLost,
    isFinished,
    isLive,
} from "@/tournament/state";

interface TournamentActions {
    readonly deleteTournament: () => void;
    readonly finishTournament: () => void;
    readonly renameTournament: (name: string) => void;
    readonly returnToGame: () => void;
    readonly selectTab: (tab: TournamentTab) => void;
    readonly sendChat: (text: string) => boolean;
    readonly setChatOpen: (open: boolean) => void;
    readonly showAllPlayed: () => void;
}

interface TournamentPage {
    readonly actions: TournamentActions;
    readonly config: TournamentConfig | null;
    readonly container: HTMLElement;
    readonly state: TournamentState;
    readonly tournamentId: string;
}

interface RecoveryLink {
    href: string;
    label: string;
}

const RELOADABLE_PAGE_ERRORS: ReadonlySet<string> = new Set([
    PAGE_ERROR.GAME_START_INVALID,
    PAGE_ERROR.PAGE_SETUP_FAILED,
]);

function backToLobbyLink(): RecoveryLink {
    return { href: "/", label: t("common.back_to_lobby") };
}

function reloadLink(): RecoveryLink {
    return { href: window.location.pathname, label: t("common.reload") };
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

function noticeTemplate(state: TournamentState): TemplateResult | typeof nothing {
    if (state.pageError) {
        const links = RELOADABLE_PAGE_ERRORS.has(state.pageError)
            ? [reloadLink(), backToLobbyLink()]
            : [backToLobbyLink()];
        return alertTemplate("error", describeTournamentError(state.pageError), links);
    }
    if (isConnectionLost(state)) {
        return alertTemplate("warning", t("tournament.connection_lost"), [
            reloadLink(),
            backToLobbyLink(),
        ]);
    }
    return nothing;
}

function sectionCount(count: number): TemplateResult {
    return html`<span class="tournament-section-count">${t("tournament.section_count", { total: count })}</span>`;
}

function startGameTemplate(config: TournamentConfig | null): TemplateResult | typeof nothing {
    if (!config?.isOwner) {
        return nothing;
    }
    return html`<button type="button" class="tournament-start-game" disabled>
        ${t("tournament.owner.start_game")}
    </button>`;
}

function currentGamesBodyTemplate(state: TournamentState): TemplateResult {
    if (!state.joined) {
        return listLoadingTemplate("rows", 2);
    }
    if (state.games.length === 0) {
        return html`<p class="tournament-quiet">${t("tournament.current.empty")}</p>`;
    }
    return currentGameRowsTemplate(state.games);
}

function currentGamesTemplate(page: TournamentPage): TemplateResult {
    const { config, state } = page;
    return html`<section class="lobby-section tournament-current" aria-labelledby="tournament-games-title">
        <div class="lobby-section-header tournament-current-header">
            <h2 id="tournament-games-title">
                ${t("current_games.title")} ${state.games.length === 0 ? nothing : sectionCount(state.games.length)}
            </h2>
            ${startGameTemplate(config)}
        </div>
        ${currentGamesBodyTemplate(state)}
    </section>`;
}

function onlineTemplate(state: TournamentState): TemplateResult {
    const names = formatList(state.players);
    return html`<details class="tournament-fold tournament-online">
        <summary>
            <span class="tournament-fold-title">${t("tournament.online_title")}</span>
            <span class="tournament-fold-count">${state.players.length}</span>
            <span class="tournament-fold-peek" aria-hidden="true">${names}</span>
        </summary>
        <p class="tournament-roster">${names}</p>
    </details>`;
}

function chatPeekTemplate(entry: ChatEntry | undefined): TemplateResult | typeof nothing {
    if (entry === undefined) {
        return nothing;
    }
    return html`<span class="tournament-fold-peek"
        ><b>${entry.sender}</b> ${entry.text}</span
    >`;
}

function chatTemplate(page: TournamentPage): TemplateResult {
    const { actions, config, state } = page;
    function toggle(event: Event): void {
        if (event.currentTarget instanceof HTMLDetailsElement) {
            actions.setChatOpen(event.currentTarget.open);
        }
    }
    const humanLines = state.chatMessages.filter((entry) => entry.sender !== LOG_TYPE_SYSTEM);
    return html`<details class="tournament-fold tournament-chat" ?open=${state.chatOpen} @toggle=${toggle}>
        <summary>
            <span class="tournament-fold-title">${t("tournament.chat_title")}</span>
            ${
                state.chatUnread === 0
                    ? nothing
                    : html`<span class="tournament-unread">${t("tournament.chat.unread", { count: state.chatUnread })}</span>`
            }
            ${state.chatOpen ? nothing : chatPeekTemplate(humanLines.at(-1))}
        </summary>
        ${chatLogTemplate(state.chatMessages)}
        ${chatComposerTemplate({ chatMaxLength: config?.chatMaxLength ?? 0, enabled: isLive(state), send: actions.sendChat })}
    </details>`;
}

function finishedTemplate(finishedAt: Date): TemplateResult {
    return html`<span class="tournament-finished">
        ${t("tournament.finished_on", { date: formatDate(finishedAt) })}
    </span>`;
}

function connectingTemplate(state: TournamentState): TemplateResult | typeof nothing {
    if (state.finishedAt !== null) {
        return finishedTemplate(state.finishedAt);
    }
    if (state.pageError) {
        return nothing;
    }
    const connecting = !isLive(state) && !isConnectionLost(state);
    return html`<span class="connection-status status-connecting tournament-connecting ${connecting ? "" : "is-idle"}" role="status">
        <span class="connection-status-text">
            <span class="connection-status-label">${connecting ? t("tournament.connecting") : nothing}</span>
            <span class="connection-status-sizer" aria-hidden="true">${t("tournament.connecting")}</span>
        </span>
    </span>`;
}

function panelsTemplate(page: TournamentPage): TemplateResult | typeof nothing {
    const { actions, state } = page;
    if (isFinished(state)) {
        return playedGamesTemplate(state.played, state.playedExpanded, actions.showAllPlayed);
    }
    if (!state.joined) {
        return isConnectionLost(state)
            ? nothing
            : html`${currentGamesTemplate(page)} ${playedGamesTemplate(null, false, actions.showAllPlayed)}`;
    }
    return html`
        ${currentGamesTemplate(page)}
        ${playedGamesTemplate(state.played, state.playedExpanded, actions.showAllPlayed)}
        <div class="tournament-side">
            ${isConnectionLost(state) ? nothing : onlineTemplate(state)}
            ${chatTemplate(page)}
        </div>
    `;
}

const TAB_LABELS: Record<TournamentTab, MessageKey> = {
    settings: "tournament.tab.settings",
    tournament: "tournament.tab.tournament",
};

function tabsTemplate(page: TournamentPage): TemplateResult | typeof nothing {
    const { actions, config, state } = page;
    if (config === null || !config.isOwner || state.pageError) {
        return nothing;
    }
    return html`
        <div class="lobby-tabs" role="tablist">
            ${TOURNAMENT_TABS.map(
                (tab) => html`
                    <button type="button" role="tab" id="tournament-tab-${tab}" aria-controls="tournament-panel" aria-selected=${tab === state.tab ? "true" : "false"} @click=${() => actions.selectTab(tab)}>
                        ${t(TAB_LABELS[tab])}
                    </button>
                `,
            )}
        </div>
    `;
}

function isEntering(state: TournamentState): boolean {
    return (
        !state.joined && !isFinished(state) && state.pageError === null && !isConnectionLost(state)
    );
}

function nameTemplate(state: TournamentState): TemplateResult | string {
    if (state.name !== null) {
        return state.name;
    }
    if (state.pageError === null) {
        return html`<span class="list-loading-bar tournament-name-loading" aria-hidden="true"></span>`;
    }
    return t("tournament.fallback_name");
}

function returnToGameTemplate(page: TournamentPage): TemplateResult | typeof nothing {
    const { liveGame } = page.state;
    if (!liveGame.playing) {
        return nothing;
    }
    return html`<div class="tournament-return">
        <button
            type="button"
            class="tournament-return-btn"
            ?disabled=${liveGame.returning}
            aria-busy=${liveGame.returning ? "true" : "false"}
            @click=${page.actions.returnToGame}
        >
            ${t("tournament.return_to_game")}
        </button>
        ${
            liveGame.returnFailed
                ? html`<p class="tournament-return-error" role="alert">${t("common.return_failed")}</p>`
                : nothing
        }
    </div>`;
}

function headerTemplate(page: TournamentPage): TemplateResult {
    const { state } = page;
    return html`
        <section class="lobby-section">
            <div class="lobby-section-header tournament-header">
                <h2 class="tournament-name">${nameTemplate(state)}</h2>
                ${connectingTemplate(state)}
            </div>
            ${tabsTemplate(page)}
        </section>
    `;
}

function renameFormTemplate(page: TournamentPage, config: TournamentConfig): TemplateResult {
    const { actions, state } = page;
    function submitRename(event: SubmitEvent): void {
        event.preventDefault();
        const form = event.currentTarget;
        const input = form instanceof HTMLFormElement ? form.elements.namedItem("name") : null;
        if (input instanceof HTMLInputElement) {
            actions.renameTournament(input.value);
        }
    }
    return html`
        <label for="tournament-rename-name">${t("tournaments.name_label")}</label>
        <form class="lobby-tournament-form" @submit=${submitRename}>
            <input type="text" id="tournament-rename-name" name="name" .value=${state.name ?? config.name} required maxlength=${config.nameMaxLength} autocomplete="off" />
            <button type="submit" ?disabled=${state.ownerBusy}>${t("tournament.owner.rename")}</button>
        </form>
    `;
}

function deleteTemplate(page: TournamentPage): TemplateResult {
    const { actions, state } = page;
    function submitDelete(event: SubmitEvent): void {
        event.preventDefault();
        actions.deleteTournament();
    }
    return html`
        <details class="tournament-delete">
            <summary>${t("tournament.owner.delete.open")}</summary>
            <form @submit=${submitDelete}>
                <p>${t("tournament.owner.delete.warning")}</p>
                <button type="submit" ?disabled=${state.ownerBusy}>${t("tournament.owner.delete.confirm")}</button>
            </form>
        </details>
    `;
}

function finishTemplate(page: TournamentPage): TemplateResult | typeof nothing {
    const { actions, state } = page;
    if (isFinished(state)) {
        return nothing;
    }
    function submitFinish(event: SubmitEvent): void {
        event.preventDefault();
        actions.finishTournament();
    }
    return html`
        <details class="tournament-finish">
            <summary>${t("tournament.owner.finish.open")}</summary>
            <form @submit=${submitFinish}>
                <p>${t("tournament.owner.finish.warning")}</p>
                <button type="submit" ?disabled=${state.ownerBusy}>${t("tournament.owner.finish.confirm")}</button>
            </form>
        </details>
    `;
}

function settingsTemplate(page: TournamentPage, config: TournamentConfig): TemplateResult {
    const { state } = page;
    return html`
        <section class="lobby-section tournament-settings" id="tournament-panel" role="tabpanel" aria-labelledby="tournament-tab-settings">
            ${
                state.ownerError === null
                    ? nothing
                    : html`<div class="lobby-alert" role="alert"><p>${t(state.ownerError)}</p></div>`
            }
            ${renameFormTemplate(page, config)} ${finishTemplate(page)} ${deleteTemplate(page)}
        </section>
    `;
}

function tournamentPanelTemplate(page: TournamentPage): TemplateResult {
    const { state } = page;
    return html`
        <div class="tournament" id="tournament-panel" role=${page.config?.isOwner ? "tabpanel" : nothing} aria-labelledby=${page.config?.isOwner ? "tournament-tab-tournament" : nothing}>
            ${noticeTemplate(state)}
            ${state.pageError ? nothing : panelsTemplate(page)}
        </div>
    `;
}

function bodyTemplate(page: TournamentPage): TemplateResult {
    const { config, state } = page;
    if (state.tab === "settings" && config?.isOwner && !state.pageError) {
        return settingsTemplate(page, config);
    }
    return tournamentPanelTemplate(page);
}

function renderTournament(page: TournamentPage): void {
    const { container, state } = page;
    document.title = t("page.title.with_page", {
        page: state.name ?? t("tournament.fallback_name"),
    });
    render(
        html`<div class="tournament-page ${isEntering(state) ? "tournament-page--entering" : ""}">
            ${headerTemplate(page)}
            ${returnToGameTemplate(page)}
            ${bodyTemplate(page)}
        </div>`,
        container,
    );
    scrollChatToLatest(container, state.chatMessages.length);
}

export { renderTournament };
export type { TournamentActions, TournamentPage };
