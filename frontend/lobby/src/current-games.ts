import { type TemplateResult, html, nothing } from "lit-html";

import { isRecord } from "@/api";
import { formatTime, t } from "@/i18n";
import { readString } from "@/lobby-socket";

export interface CurrentGame {
    readonly gameId: string;
    readonly players: readonly string[];
    readonly startedAt: Date;
}

export function readNames(message: Record<string, unknown>): string[] | null {
    const { players } = message;
    if (!Array.isArray(players) || !players.every((name) => typeof name === "string")) {
        return null;
    }
    return players;
}

export function readEpochTime(value: unknown): Date {
    return typeof value === "number" ? new Date(value * 1000) : new Date();
}

export function readCurrentGame(message: Record<string, unknown>, at: Date): CurrentGame | null {
    const gameId = readString(message, "game_id");
    const players = readNames(message);
    if (gameId === null || players === null) {
        return null;
    }
    return { gameId, players, startedAt: at };
}

export function readCurrentGames(message: Record<string, unknown>): CurrentGame[] {
    const { games } = message;
    if (!Array.isArray(games)) {
        return [];
    }
    return games
        .filter((game): game is Record<string, unknown> => isRecord(game))
        .map((game) => readCurrentGame(game, readEpochTime(game.started_at)))
        .filter((game): game is CurrentGame => game !== null);
}

function gameCard(game: CurrentGame, index: number): TemplateResult {
    const names = game.players.join(", ");
    const last = game.players.length - 1;
    return html`<article class="lobby-room-card" style="--card-index: ${index}">
        <div class="lobby-room-header">
            <span class="lobby-table-name">${t("current_games.table", { number: index + 1 })}</span>
            <span class="lobby-room-count">${formatTime(game.startedAt)}</span>
        </div>
        <div class="lobby-table-vis" aria-hidden="true">
            ${game.players.map(() => html`<span class="lobby-seat filled"></span>`)}
        </div>
        <p class="lobby-room-players">
            <span class="lobby-room-names" title=${names}>
                ${game.players.map((name, seat) => html`${seat > 0 ? " " : ""}<span class="current-game-player">${name}${seat < last ? "," : ""}</span>`)}
            </span>
        </p>
    </article>`;
}

function gamesListTemplate(games: readonly CurrentGame[]): TemplateResult {
    if (games.length === 0) {
        return html`<div class="lobby-empty lobby-empty--inline lobby-muted">
            <p class="lobby-empty-title">${t("current_games.empty")}</p>
        </div>`;
    }
    return html`<div class="lobby-grid">${games.map((game, index) => gameCard(game, index))}</div>`;
}

export function currentGamesTemplate(
    games: readonly CurrentGame[] | null,
    titleId: string,
): TemplateResult {
    return html`<section class="lobby-section current-games" aria-labelledby=${titleId}>
        <div class="lobby-section-header">
            <h2 id=${titleId}>${t("current_games.title")}</h2>
            ${
                games === null
                    ? nothing
                    : html`<small class="lobby-table-count">${t("current_games.count", { count: games.length })}</small>`
            }
        </div>
        ${games === null ? nothing : gamesListTemplate(games)}
    </section>`;
}
