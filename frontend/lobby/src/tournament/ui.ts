import { type TemplateResult, html, nothing, render } from "lit-html";

import { chatComposerTemplate, chatLogTemplate, scrollChatToLatest } from "@/chat";
import { t } from "@/i18n";
import { describeTournamentError } from "@/tournament/handlers";
import { PAGE_ERROR, type TournamentState, isConnectionLost, isLive } from "@/tournament/state";

interface TournamentPage {
    chatMaxLength: number;
    container: HTMLElement;
    sendChat: (text: string) => boolean;
    state: TournamentState;
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
    const { chatMaxLength, sendChat, state } = page;
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
                ${chatComposerTemplate({ chatMaxLength, enabled: isLive(state), send: sendChat })}
            </section>
        </div>
    `;
}

function renderTournament(page: TournamentPage): void {
    const { container, state } = page;
    render(
        html`
            <div class="tournament">
                ${noticeTemplate(state)}
                ${state.pageError ? nothing : panelsTemplate(page)}
            </div>
        `,
        container,
    );
    scrollChatToLatest(container, state.chatMessages.length);
}

export { renderTournament };
