import { type TemplateResult, html, nothing, render } from "lit-html";

import { pageFailedView } from "@/app/page-failed";
import { formatDuration } from "@/format-duration";
import { gameTypeNameKey } from "@/game-types";
import { copyReplayLink } from "@/games-history";
import { type HistoryGame, type HistoryPlayer, type HistoryState } from "@/history/state";
import { formatDateTime, formatNumber, t, tParts } from "@/i18n";
import { listLoadingTemplate } from "@/list-loading";

function finalScoreClass(finalScore: number): string {
    if (finalScore > 0) {
        return "games-pts games-pts--positive";
    }
    return finalScore < 0 ? "games-pts games-pts--negative" : "games-pts";
}

function finalScoreText(finalScore: number): string {
    const text = formatNumber(finalScore, { maximumFractionDigits: 1, minimumFractionDigits: 1 });
    return finalScore > 0 ? `+${text}` : text;
}

function standingClass(player: HistoryPlayer): string {
    return `games-standing${player.isWinner ? " games-standing--winner" : ""}${
        player.isViewer ? " games-standing--me" : ""
    }`;
}

function standingTemplate(player: HistoryPlayer, rank: number): TemplateResult {
    return html`<div class=${standingClass(player)}>
        <span class="games-rank">${rank}</span>
        <span class="games-name">${player.name}</span>
        ${player.isViewer ? html`<span class="games-you">${t("history.you")}</span>` : nothing}
        ${
            player.score === null
                ? nothing
                : html`<span class="games-score" title=${t("history.legend.points")}
                      >${formatNumber(player.score)}</span
                  >`
        }
        ${
            player.finalScore === null
                ? nothing
                : html`<span
                      class=${finalScoreClass(player.finalScore)}
                      title=${t("history.legend.result")}
                      >${finalScoreText(player.finalScore)}</span
                  >`
        }
    </div>`;
}

function gameTypeLabel(game: HistoryGame, number: number): TemplateResult | typeof nothing {
    const nameKey = gameTypeNameKey(game.gameType);
    if (nameKey === null) {
        return nothing;
    }
    return html`<span class="games-wind" aria-hidden="true">${game.wind ?? ""}</span>
        <span class="games-type" id="games-type-${number}">${t(nameKey)}</span>`;
}

function metaTemplate(game: HistoryGame): TemplateResult {
    return html`<div class="games-meta">
        ${
            game.durationSeconds === null
                ? nothing
                : html`<span class="games-meta-tag">${formatDuration(game.durationSeconds)}</span>`
        }
        ${
            game.numRoundsPlayed
                ? html`<span class="games-meta-tag"
                      >${t("history.rounds", { count: game.numRoundsPlayed })}</span
                  >`
                : nothing
        }
    </div>`;
}

function actionsTemplate(game: HistoryGame, number: number): TemplateResult {
    return html`<div class="games-card-actions">
        <span class="games-copy-status" role="status"></span>
        <button
            class="games-copy-btn"
            data-replay-url=${game.replayUrl}
            title=${t("history.copy_link")}
            aria-label=${t("history.copy_link")}
            type="button"
            @click=${copyReplayLink}
        >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <rect
                    x="5.5"
                    y="5.5"
                    width="9"
                    height="9"
                    rx="1.5"
                    stroke="currentColor"
                    stroke-width="1.5"
                />
                <path
                    d="M11 1.5H3A1.5 1.5 0 0 0 1.5 3v8"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linecap="round"
                />
            </svg>
        </button>
        <a
            class="games-card-link"
            href=${game.viewerReplayUrl}
            id="games-replay-${number}"
            aria-labelledby="games-replay-${number} games-type-${number} games-time-${number}"
            >${t("history.view_replay")}</a
        >
    </div>`;
}

function gameCard(game: HistoryGame, index: number): TemplateResult {
    const number = index + 1;
    return html`<article class="games-card">
        <header class="games-card-header">
            <div class="games-card-label">${gameTypeLabel(game, number)}</div>
            <time
                class="games-time"
                id="games-time-${number}"
                datetime=${game.startedAt.toISOString()}
                >${formatDateTime(game.startedAt)}</time
            >
        </header>

        <div class="games-standings">
            <div class="games-standings-legend" aria-hidden="true">
                <span>${t("history.legend.points")}</span>
                <span>${t("history.legend.result")}</span>
            </div>
            ${game.players.map((player, rank) => standingTemplate(player, rank + 1))}
        </div>

        <footer class="games-card-footer">
            ${metaTemplate(game)} ${actionsTemplate(game, number)}
        </footer>
    </article>`;
}

function emptyHistoryHint(): TemplateResult {
    const quickMatch = html`<a href="/matchmaking">${t("history.empty_quick_match")}</a>`;
    const table = html`<a href="/">${t("history.empty_table")}</a>`;
    return html`<p class="lobby-empty-hint">
        ${tParts("history.empty_hint", { quick_match: quickMatch, table })}
    </p>`;
}

function gamesTemplate(games: readonly HistoryGame[]): TemplateResult {
    return games.length > 0
        ? html`<div class="games-list">${games.map((game, index) => gameCard(game, index))}</div>`
        : html`<div class="lobby-empty lobby-empty--boxed">
                  <p class="lobby-empty-title">${t("history.empty_title")}</p>
                  ${emptyHistoryHint()}
              </div>`;
}

function historyTemplate(state: HistoryState): TemplateResult {
    if (state.loadFailed) {
        return pageFailedView();
    }
    const { games } = state;
    return html`<section class="lobby-section">
        <div class="lobby-section-header">
            <h2>${t("history.recent_games")}</h2>
            ${
                games && games.length > 0
                    ? html`<small class="lobby-table-count"
                          >${t("history.shown_count", { count: games.length })}</small
                      >`
                    : nothing
            }
        </div>

        ${games ? gamesTemplate(games) : listLoadingTemplate("cards", 3)}
    </section>`;
}

export function renderHistory(host: HTMLElement, state: HistoryState): void {
    document.title = t("page.title.with_page", { page: t("nav.history") });
    render(historyTemplate(state), host);
}
