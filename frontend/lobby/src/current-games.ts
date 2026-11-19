import { type TemplateResult, html, nothing } from "lit-html";

import { isRecord } from "@/api";
import { gameTypeNameKey, gameTypeWind } from "@/game-types";
import { formatTime, t } from "@/i18n";
import { readString } from "@/lobby-socket";
import { seatNamesTemplate } from "@/seat-names";

export interface CurrentGame {
    readonly gameId: string;
    readonly gameType: string | null;
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
    return { gameId, gameType: readString(message, "game_type"), players, startedAt: at };
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

function windTemplate(gameType: string | null): TemplateResult | typeof nothing {
    const nameKey = gameType === null ? null : gameTypeNameKey(gameType);
    const wind = gameType === null ? null : gameTypeWind(gameType);
    if (nameKey === null || wind === null) {
        return nothing;
    }
    return html`<abbr class="current-game-wind" title=${t(nameKey)}>${wind}</abbr>`;
}

const ELAPSED_REDRAW_MS = 20_000;
const MS_PER_MINUTE = 60_000;
const MINUTES_PER_HOUR = 60;

function formatElapsed(startedAt: Date, now: Date): string {
    const minutes = Math.floor((now.getTime() - startedAt.getTime()) / MS_PER_MINUTE);
    if (minutes < 1) {
        return t("current_games.elapsed_new");
    }
    if (minutes < MINUTES_PER_HOUR) {
        return t("current_games.elapsed_minutes", { minutes });
    }
    return t("current_games.elapsed_hours", {
        hours: Math.floor(minutes / MINUTES_PER_HOUR),
        minutes: minutes % MINUTES_PER_HOUR,
    });
}

export function redrawElapsedTimes(redraw: () => void): () => void {
    const timer = setInterval(redraw, ELAPSED_REDRAW_MS);
    return () => clearInterval(timer);
}

function gameRow(game: CurrentGame, now: Date): TemplateResult {
    return html`<li class="current-game">
        <span class="current-game-meta">
            ${windTemplate(game.gameType)}
            <time datetime=${game.startedAt.toISOString()} title=${formatTime(game.startedAt)}
                >${formatElapsed(game.startedAt, now)}</time
            >
        </span>
        ${seatNamesTemplate(game.players)}
    </li>`;
}

function gamesListTemplate(games: readonly CurrentGame[]): TemplateResult {
    if (games.length === 0) {
        return html`<div class="lobby-empty lobby-empty--boxed">
            <p class="lobby-empty-title">${t("current_games.empty")}</p>
            <p class="lobby-empty-hint">${t("current_games.empty_hint")}</p>
        </div>`;
    }
    const now = new Date();
    return html`<ul class="current-games-list">
        ${games.map((game) => gameRow(game, now))}
    </ul>`;
}

export function currentGamesTemplate(
    games: readonly CurrentGame[] | null,
    titleId: string,
): TemplateResult {
    return html`<section class="lobby-section current-games" aria-labelledby=${titleId}>
        <div class="lobby-section-header">
            <h2 id=${titleId}>${t("current_games.title")}</h2>
            ${
                games === null || games.length === 0
                    ? nothing
                    : html`<small class="lobby-table-count">${t("current_games.count", { count: games.length })}</small>`
            }
        </div>
        ${games === null ? nothing : gamesListTemplate(games)}
    </section>`;
}
