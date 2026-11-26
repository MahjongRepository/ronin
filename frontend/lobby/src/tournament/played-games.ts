import { type TemplateResult, html, nothing } from "lit-html";

import { isRecord } from "@/api";
import { readEpochTime, readNames } from "@/current-games";
import {
    type MessageKey,
    formatDateTime,
    formatList,
    formatNumber,
    formatTime,
    reportI18nError,
    t,
} from "@/i18n";
import { listLoadingTemplate } from "@/list-loading";
import { readString } from "@/lobby-socket";

const END_REASON_COMPLETED = "completed";
const FINAL_SCORE_TENTHS = 10;
const PLAYED_SHOWN_COLLAPSED = 5;
const PLAYED_SHOWN_COLLAPSED_PHONE = 3;
const PLACE_KEYS = [
    "tournament.played.place.first",
    "tournament.played.place.second",
    "tournament.played.place.third",
    "tournament.played.place.fourth",
] as const satisfies readonly MessageKey[];

interface UnrankedOutcome {
    readonly countKey: MessageKey;
    readonly labelKey: MessageKey;
}

const UNRANKED_OUTCOMES: Record<string, UnrankedOutcome> = {
    abandoned: {
        countKey: "tournament.played.abandoned_count",
        labelKey: "tournament.played.outcome.abandoned",
    },
    error: {
        countKey: "tournament.played.error_count",
        labelKey: "tournament.played.outcome.error",
    },
};

interface RankedPlayer {
    readonly name: string;
    /** The place from 1, shared by tied players; by order for a game recorded before places were. */
    readonly place: number;
    /** The uma/oka-adjusted final score in points, to its tenth. */
    readonly finalScore: number;
}

export interface PlayedGame {
    readonly endReason: string;
    readonly endedAt: Date;
    readonly gameId: string;
    /** The players East to North. */
    readonly players: readonly string[];
    /** The standings in placement order for a completed game; null for any other end. */
    readonly ranked: readonly RankedPlayer[] | null;
}

function readRankedPlayer(entry: unknown, index: number): RankedPlayer | null {
    if (!isRecord(entry) || typeof entry.name !== "string") {
        return null;
    }
    const { final_score: finalScore, place } = entry;
    if (typeof finalScore !== "number") {
        return null;
    }
    return {
        finalScore: finalScore / FINAL_SCORE_TENTHS,
        name: entry.name,
        place: typeof place === "number" ? place : index + 1,
    };
}

function readRanked(message: Record<string, unknown>): RankedPlayer[] | null {
    const { result } = message;
    if (message.end_reason !== END_REASON_COMPLETED || !Array.isArray(result)) {
        return null;
    }
    const ranked = result.map(readRankedPlayer);
    return ranked.every((player): player is RankedPlayer => player !== null) ? ranked : null;
}

/** Reads a `game_ended` event or a `joined` played entry, which share one shape. */
export function readPlayedGame(message: Record<string, unknown>): PlayedGame | null {
    const gameId = readString(message, "game_id");
    const endReason = readString(message, "end_reason");
    const players = readNames(message);
    if (gameId === null || endReason === null || players === null) {
        return null;
    }
    return {
        endReason,
        endedAt: readEpochTime(message.ended_at),
        gameId,
        players,
        ranked: readRanked(message),
    };
}

export function readPlayedGames(message: Record<string, unknown>): PlayedGame[] {
    const { played } = message;
    if (!Array.isArray(played)) {
        return [];
    }
    return played
        .filter((game): game is Record<string, unknown> => isRecord(game))
        .map(readPlayedGame)
        .filter((game): game is PlayedGame => game !== null);
}

export function addPlayedGame(
    played: readonly PlayedGame[],
    game: PlayedGame,
): readonly PlayedGame[] {
    return [game, ...played.filter((known) => known.gameId !== game.gameId)].toSorted(
        (earlier, later) => later.endedAt.getTime() - earlier.endedAt.getTime(),
    );
}

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

function endedText(endedAt: Date, now: Date): string {
    return endedAt.toDateString() === now.toDateString()
        ? formatTime(endedAt)
        : formatDateTime(endedAt);
}

function unrankedOutcome(endReason: string): string {
    const outcome = UNRANKED_OUTCOMES[endReason];
    if (outcome === undefined) {
        reportI18nError(`tournament.played.outcome.${endReason}`, "unknown game end reason");
        return t("tournament.played.outcome.unknown");
    }
    return t(outcome.labelKey);
}

function rankedTemplate(ranked: readonly RankedPlayer[]): TemplateResult {
    return html`<ol class="played-game-places">
        ${ranked.map(
            (player) => html`<li class="played-game-place">
                <span class="played-game-rank">${formatNumber(player.place)}</span>
                <span class="played-game-name" title=${player.name}>${player.name}</span>
                <span class=${finalScoreClass(player.finalScore)}
                    >${finalScoreText(player.finalScore)}</span
                >
            </li>`,
        )}
    </ol>`;
}

function unrankedTemplate(game: PlayedGame): TemplateResult {
    return html`<p class="played-game-unranked">
        <span class="played-game-outcome">${unrankedOutcome(game.endReason)}</span>
        <span class="played-game-names">${formatList(game.players)}</span>
    </p>`;
}

function replayLink(gameId: string): TemplateResult {
    return html`<a
        href="/play/history/${encodeURIComponent(gameId)}"
        id="played-replay-${gameId}"
        aria-labelledby="played-replay-${gameId} played-ended-${gameId}"
        class="lobby-join-btn lobby-join-btn--ghost played-game-replay"
        >${t("tournament.played.replay")}</a
    >`;
}

function playedRow(game: PlayedGame, now: Date): TemplateResult {
    return html`<li class="played-game">
        <time
            class="played-game-ended"
            id="played-ended-${game.gameId}"
            datetime=${game.endedAt.toISOString()}
            >${endedText(game.endedAt, now)}</time
        >
        ${game.ranked === null ? unrankedTemplate(game) : rankedTemplate(game.ranked)}
        ${game.ranked === null ? nothing : replayLink(game.gameId)}
    </li>`;
}

function breakdownText(played: readonly PlayedGame[]): string | null {
    const completed = played.filter((game) => game.ranked !== null).length;
    if (completed === played.length) {
        return null;
    }
    const unranked = played.filter((game) => game.ranked === null);
    const parts = Object.entries(UNRANKED_OUTCOMES)
        .map(([endReason, outcome]) => ({
            count: unranked.filter((game) => game.endReason === endReason).length,
            outcome,
        }))
        .filter(({ count }) => count > 0)
        .map(({ count, outcome }) => t(outcome.countKey, { count }));
    return [t("tournament.played.completed_count", { count: completed }), ...parts].join(
        t("tournament.played.breakdown_separator"),
    );
}

function moreButton(
    played: readonly PlayedGame[],
    showAll: () => void,
): TemplateResult | typeof nothing {
    if (played.length <= PLAYED_SHOWN_COLLAPSED_PHONE) {
        return nothing;
    }
    const phoneOnly = played.length <= PLAYED_SHOWN_COLLAPSED;
    return html`<button
        type="button"
        class="played-games-more ${phoneOnly ? "played-games-more--phone" : ""}"
        @click=${showAll}
    >
        ${t("tournament.played.show_all", { count: played.length })}
    </button>`;
}

function playedListTemplate(
    played: readonly PlayedGame[],
    expanded: boolean,
    showAll: () => void,
): TemplateResult {
    const now = new Date();
    const shown = expanded ? played : played.slice(0, PLAYED_SHOWN_COLLAPSED);
    return html`<div class="played-games ${expanded ? "played-games--expanded" : ""}">
        <div class="played-games-head" aria-hidden="true">
            <span>${t("tournament.played.ended")}</span>
            <span class="played-games-head-places">
                ${PLACE_KEYS.map((key) => html`<span>${t(key)}</span>`)}
            </span>
        </div>
        <ol class="played-games-list">
            ${shown.map((game) => playedRow(game, now))}
        </ol>
        ${expanded ? nothing : moreButton(played, showAll)}
    </div>`;
}

function playedGamesBodyTemplate(
    played: readonly PlayedGame[] | null,
    expanded: boolean,
    showAll: () => void,
): TemplateResult {
    if (played === null) {
        return listLoadingTemplate("rows", 3);
    }
    if (played.length === 0) {
        return html`<p class="tournament-quiet">${t("tournament.played.empty")}</p>`;
    }
    return playedListTemplate(played, expanded, showAll);
}

/** Draws the game history; null `played` is the history not loaded yet. */
export function playedGamesTemplate(
    played: readonly PlayedGame[] | null,
    expanded: boolean,
    showAll: () => void,
): TemplateResult {
    const count = played?.length ?? 0;
    const breakdown = played === null ? null : breakdownText(played);
    return html`<section class="lobby-section tournament-played" aria-labelledby="tournament-played-title">
        <div class="lobby-section-header">
            <h2 id="tournament-played-title">
                ${t("tournament.played.title")}
                ${
                    count === 0
                        ? nothing
                        : html`<span class="tournament-section-count"
                              >${t("tournament.section_count", { total: count })}</span
                          >`
                }
            </h2>
            ${breakdown === null ? nothing : html`<small class="lobby-table-count">${breakdown}</small>`}
        </div>
        ${playedGamesBodyTemplate(played, expanded, showAll)}
    </section>`;
}
