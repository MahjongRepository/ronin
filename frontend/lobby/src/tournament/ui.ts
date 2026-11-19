import { type TemplateResult, html, nothing, render } from "lit-html";

import { chatComposerTemplate, chatLogTemplate, scrollChatToLatest } from "@/chat";
import { t, tParts } from "@/i18n";
import { describeTournamentError } from "@/tournament/handlers";
import {
    PAGE_ERROR,
    type TournamentConfig,
    type TournamentState,
    isConnectionLost,
    isLive,
} from "@/tournament/state";

interface TournamentActions {
    readonly deleteTournament: () => void;
    readonly renameTournament: (name: string) => void;
    readonly sendChat: (text: string) => boolean;
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

function onlineListTemplate(state: TournamentState): TemplateResult | typeof nothing {
    if (isConnectionLost(state)) {
        return nothing;
    }
    if (!isLive(state)) {
        return html`
            <p class="connection-status status-connecting" role="status">${t("tournament.connecting")}</p>
        `;
    }
    return html`
        <div class="room-player-list">
            ${state.players.map(
                (name) => html`
                    <div class="room-player-item">
                        <span class="room-player-name">${name}</span>
                    </div>
                `,
            )}
        </div>
    `;
}

function onlineTitle(state: TournamentState): string {
    if (!isLive(state)) {
        return t("tournament.online_title");
    }
    return t("tournament.online_count", { count: state.players.length });
}

function panelsTemplate(page: TournamentPage): TemplateResult {
    const { actions, config, state } = page;
    const chatMaxLength = config?.chatMaxLength ?? 0;
    return html`
        <div class="room-content">
            <section class="room-panel" aria-labelledby="tournament-online-title">
                <h3 class="room-panel-title" id="tournament-online-title">
                    ${onlineTitle(state)}
                </h3>
                ${onlineListTemplate(state)}
            </section>
            <section class="room-panel room-chat-panel" aria-labelledby="tournament-chat-title">
                <h3 class="room-panel-title" id="tournament-chat-title">${t("tournament.chat_title")}</h3>
                ${chatLogTemplate(state.chatMessages)}
                ${chatComposerTemplate({ chatMaxLength, enabled: isLive(state), send: actions.sendChat })}
            </section>
        </div>
    `;
}

function headerTemplate(state: TournamentState, config: TournamentConfig | null): TemplateResult {
    return html`
        <section class="lobby-section">
            <div class="lobby-section-header">
                <h2 class="tournament-name">${state.name ?? t("tournament.fallback_name")}</h2>
            </div>
            ${
                config === null
                    ? nothing
                    : html`<label for="tournament-share-link">${t("tournament.share_link")}
                          <input type="text" id="tournament-share-link" .value=${config.shareUrl} readonly spellcheck="false" />
                      </label>`
            }
        </section>
    `;
}

function code(text: string): TemplateResult {
    return html`<code>${text}</code>`;
}

function apiHintsTemplate(tournamentId: string): TemplateResult {
    return html`
        <ul class="tournament-owner-api">
            <li>${tParts("tournament.owner.id", { value: code(tournamentId) })}</li>
            <li>${tParts("tournament.owner.start_games", { value: code(`POST /api/tournaments/${tournamentId}/games`) })}</li>
            <li>${tParts("tournament.owner.state", { value: code(`GET /api/tournaments/${tournamentId}`) })}</li>
            <li>${tParts("tournament.owner.events", { value: code(`/ws/tournaments/${tournamentId}/events`) })}</li>
        </ul>
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
        <form class="lobby-tournament-form" @submit=${submitRename}>
            <input type="text" name="name" .value=${state.name ?? config.name} required maxlength=${config.nameMaxLength} aria-label=${t("lobby.tournament.name_label")} autocomplete="off" />
            <button type="submit" class="outline" ?disabled=${state.ownerBusy}>${t("tournament.owner.rename")}</button>
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

function ownerTemplate(page: TournamentPage): TemplateResult | typeof nothing {
    const { config, state, tournamentId } = page;
    if (config === null || !config.isOwner) {
        return nothing;
    }
    const settingsLink = html`<a href="/settings">${t("nav.settings")}</a>`;
    return html`
        <section class="lobby-section">
            <div class="lobby-section-header">
                <h2>${t("tournament.owner.title")}</h2>
            </div>
            <p class="lobby-muted">${tParts("tournament.owner.intro", { settings: settingsLink })}</p>
            ${apiHintsTemplate(tournamentId)}
            ${
                state.ownerError === null
                    ? nothing
                    : html`<div class="lobby-alert" role="alert"><p>${t(state.ownerError)}</p></div>`
            }
            ${renameFormTemplate(page, config)} ${deleteTemplate(page)}
        </section>
    `;
}

function renderTournament(page: TournamentPage): void {
    const { config, container, state } = page;
    document.title = t("page.title.with_page", {
        page: state.name ?? t("tournament.fallback_name"),
    });
    render(
        html`
            ${headerTemplate(state, config)}
            <div class="tournament">
                ${noticeTemplate(state)}
                ${state.pageError ? nothing : panelsTemplate(page)}
            </div>
            ${state.pageError ? nothing : ownerTemplate(page)}
        `,
        container,
    );
    scrollChatToLatest(container, state.chatMessages.length);
}

export { renderTournament };
export type { TournamentActions, TournamentPage };
