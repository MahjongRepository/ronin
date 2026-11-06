import {
    type GameEndResult,
    type PlayerState,
    type TableState,
} from "@/entities/table/model/types";
import { type MessageKey, t } from "@/shared/i18n";
import { GAME_END_CAUSE, type GameEndCause } from "@/shared/protocol";

import { gameTypeName } from "./game-start-display";
import { formatDelta, formatPoints } from "./round-end-display";
import { roundName } from "./round-name";

export type ResultTone = "positive" | "negative" | "even";

/** A seat at the game's end, the seats in placement order. */
export interface GameEndSeat {
    readonly placement: string;
    readonly name: string;
    /** The final score, the leftover riichi sticks included. */
    readonly score: string;
    /** The uma/oka-adjusted result, in thousands: "+42.0". */
    readonly result: string;
    readonly resultTone: ResultTone;
    readonly isViewer: boolean;
    readonly isAiPlayer: boolean;
}

/** How the game came to its end, always as a completed game: the rule the server's engine ended it by, and where. */
export interface GameEnding {
    readonly kind: GameEndCause;
    readonly text: string;
}

/**
 * The game's end as the seating panel shows it: the game's length, how it ended, the seats in placement order with
 * their scores and uma/oka results, and where the riichi sticks left at the end went.
 */
export interface GameEndDisplayState {
    readonly gameType: string | null;
    readonly ending: GameEnding;
    readonly seats: readonly GameEndSeat[];
    readonly leftover: string | null;
}

const PLACEMENTS: readonly MessageKey[] = [
    "game.summary.rank_1",
    "game.summary.rank_2",
    "game.summary.rank_3",
    "game.summary.rank_4",
];

function placementName(index: number): string {
    const key = PLACEMENTS[index];
    return key === undefined ? t("game.summary.rank_other", { rank: index + 1 }) : t(key);
}

function tone(value: number): ResultTone {
    if (value > 0) {
        return "positive";
    }
    return value < 0 ? "negative" : "even";
}

function formatResult(finalScore: number): string {
    const digits = Math.abs(finalScore).toFixed(1);
    if (finalScore > 0) {
        return `+${digits}`;
    }
    return finalScore < 0 ? `−${digits}` : digits;
}

function playerAt(players: readonly PlayerState[], seat: number): PlayerState | undefined {
    return players.find((player) => player.seat === seat);
}

function nameAt(players: readonly PlayerState[], seat: number): string {
    return playerAt(players, seat)?.name ?? t("game.seat.fallback_name", { seat });
}

/** The sticks left at the game's end: what they paid the winner, or that the rules award them to nobody. */
function leftoverText(end: GameEndResult, players: readonly PlayerState[]): string | null {
    const { leftoverRiichiBonus, leftoverSticks, winnerSeat } = end;
    if (leftoverSticks === 0 && leftoverRiichiBonus === 0) {
        return null;
    }
    if (leftoverRiichiBonus === 0) {
        return t("game.summary.leftover_unpaid", { count: leftoverSticks });
    }
    return t("game.summary.leftover_paid", {
        count: leftoverSticks,
        name: nameAt(players, winnerSeat),
        points: formatDelta(leftoverRiichiBonus),
    });
}

/** Each cause's line, with the last round where it is known and without it where it is not. */
const ENDING_TEXTS: Readonly<
    Record<GameEndCause, { readonly withRound: MessageKey; readonly without: MessageKey }>
> = {
    [GAME_END_CAUSE.EXTENSION_LIMIT]: {
        withRound: "game.ending.extension_limit_in_round",
        without: "game.ending.extension_limit",
    },
    [GAME_END_CAUSE.LENGTH]: {
        withRound: "game.ending.length_in_round",
        without: "game.ending.length",
    },
    [GAME_END_CAUSE.TARGET_REACHED]: {
        withRound: "game.ending.target_reached_in_round",
        without: "game.ending.target_reached",
    },
    [GAME_END_CAUSE.TOBI]: {
        withRound: "game.ending.tobi_in_round",
        without: "game.ending.tobi",
    },
};

/**
 * Why the game ended, as the server's engine decided it (`endCause`), and in the round the table stands on, its last,
 * where the table is in step with the server; a table that lost step does not name it.
 */
function gameEnding(table: TableState, end: GameEndResult): GameEnding {
    const texts = ENDING_TEXTS[end.endCause];
    if (!table.inStep) {
        return { kind: end.endCause, text: t(texts.without) };
    }
    const round = roundName(table.roundWind, table.roundInWind);
    return { kind: end.endCause, text: t(texts.withRound, { round }) };
}

/**
 * The end of a table whose game ended, read from `viewerSeat` (the live player's seat, none in a replay): the seats in
 * placement order with their scores and uma/oka results as the server gave them, how the game ended and the leftover
 * riichi sticks. Null before the game ends.
 */
export function gameEndDisplay(
    table: TableState,
    viewerSeat: number | null,
): GameEndDisplayState | null {
    const end = table.gameEndResult;
    if (table.phase !== "game_ended" || end === null) {
        return null;
    }
    return {
        ending: gameEnding(table, end),
        gameType: gameTypeName(table),
        leftover: leftoverText(end, table.players),
        seats: end.standings.map((standing, index) => ({
            isAiPlayer: playerAt(table.players, standing.seat)?.isAiPlayer ?? false,
            isViewer: standing.seat === viewerSeat,
            name: nameAt(table.players, standing.seat),
            placement: placementName(index),
            result: formatResult(standing.finalScore),
            resultTone: tone(standing.finalScore),
            score: formatPoints(standing.score),
        })),
    };
}
