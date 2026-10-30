import { RIICHI_STICK_VALUE } from "@/entities/table/model/handlers/round-end";
import { requireRiichiCost, roundInWind } from "@/entities/table/model/helpers";
import {
    type GameEndResult,
    type PlayerState,
    type RoundRecord,
    type TableState,
} from "@/entities/table/model/types";

import { drawName } from "./draw-name";
import { formatDelta, formatPoints } from "./round-end-display";
import { roundName } from "./round-name";

export type StandingsTone = "positive" | "negative" | "even";

/** A seat's column of the standings, the columns in placement order. */
export interface StandingsSeat {
    readonly seat: number;
    readonly name: string;
    /** "1st" through "4th". */
    readonly placement: string;
    /** The final score, the leftover riichi sticks included. */
    readonly score: string;
    /** The uma/oka-adjusted result, in thousands: "+42.0". */
    readonly result: string;
    readonly resultTone: StandingsTone;
    /** The seat the standings are read from: the live player's, or the replay's bottom seat. */
    readonly viewer: boolean;
}

/** One seat's cell of a ledger row: its change in the round, net of its riichi deposit. */
export interface LedgerCell {
    readonly text: string;
    readonly tone: StandingsTone;
    /**
     * The seat won the round, paid its ron (dealt in, or had its kan robbed), or was liable for a winner's yakuman
     * (pao) without paying a ron.
     */
    readonly mark: "win" | "deal_in" | "pao" | null;
    readonly riichi: boolean;
    readonly dealer: boolean;
}

/** One finished round of the ledger, its cells in the columns' order. */
export interface LedgerRow {
    /** The round's place in the game's history, from 0. */
    readonly round: number;
    /** "East 1". */
    readonly name: string;
    readonly honba: number;
    /** "Ron", "Tsumo", "Double ron", or the draw's name. */
    readonly outcome: string;
    /** The outcome with who won from whom, as a sentence: "Ron by Bob from Alice". */
    readonly summary: string;
    readonly cells: readonly LedgerCell[];
}

/**
 * The riichi sticks left on the table at the game's end and where they went: the winner's score holds them, or, where
 * the game's rules award them to nobody, no score does.
 */
export interface LeftoverSticks {
    readonly sticks: number;
    readonly awarded: boolean;
    /** The points they paid, by column: the winner's, blank for the others (every column when not awarded). */
    readonly cells: readonly string[];
}

/** The final standings as the panel shows them: a column per seat, a ledger row per round, the leftover sticks. */
export interface StandingsDisplay {
    readonly seats: readonly StandingsSeat[];
    readonly ledger: readonly LedgerRow[];
    /**
     * Whether the ledger holds every round as the server played it: a row per round the server counted, from a round
     * history in step with it. The seats' scores and results are the server's either way.
     */
    readonly ledgerComplete: boolean;
    readonly leftover: LeftoverSticks | null;
}

const PLACEMENTS = ["1st", "2nd", "3rd", "4th"] as const;

function tone(value: number): StandingsTone {
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

function nameOf(players: readonly PlayerState[]): (seat: number) => string {
    return (seat) => players.find((player) => player.seat === seat)?.name ?? `Seat ${seat}`;
}

function outcomeName(record: RoundRecord): string {
    const { outcome } = record;
    if (outcome === "tsumo") {
        return "Tsumo";
    }
    if (outcome === "ron") {
        return record.winnerSeats.length > 1 ? "Double ron" : "Ron";
    }
    return outcome === "exhaustive" ? "Draw" : drawName(outcome);
}

function outcomeSummary(record: RoundRecord, name: (seat: number) => string): string {
    const title = outcomeName(record);
    if (record.winnerSeats.length === 0) {
        return title;
    }
    const winners = record.winnerSeats.map(name).join(" and ");
    const from = record.loserSeat === null ? "" : ` from ${name(record.loserSeat)}`;
    return `${title} by ${winners}${from}`;
}

function paidIn(record: RoundRecord, seat: number): number {
    return record.scoreChanges[String(seat)] ?? 0;
}

/** A seat's change in a round: its payments less the deposit, at the table's riichi cost, of a riichi that stood. */
function ledgerDelta(record: RoundRecord, seat: number, riichiCost: number): number {
    const paid = paidIn(record, seat);
    return record.riichiSeats.includes(seat) ? paid - riichiCost : paid;
}

/**
 * A cell's words: its change, else on a round with no payments, the seat's tenpai on a draw that judges it or ±0; a
 * seat that kept its points while others were paid shows nothing. A riichi deposit is a change but never a payment,
 * so it hides no other seat's tenpai.
 */
interface SeatChange {
    readonly seat: number;
    readonly delta: number;
}

function cellText(
    record: RoundRecord,
    seats: readonly number[],
    { delta, seat }: SeatChange,
): string {
    if (delta !== 0) {
        return formatDelta(delta);
    }
    if (seats.some((other) => paidIn(record, other) !== 0)) {
        return "";
    }
    if (record.tenpaiSeats !== null) {
        return record.tenpaiSeats.includes(seat) ? "Tenpai" : "Noten";
    }
    return "±0";
}

function cellMark(record: RoundRecord, seat: number): LedgerCell["mark"] {
    if (record.winnerSeats.includes(seat)) {
        return "win";
    }
    if (record.loserSeat === seat) {
        return "deal_in";
    }
    return record.paoSeats.includes(seat) ? "pao" : null;
}

/** The table a ledger reads its names, first dealer and riichi cost from, and its seats in column order. */
interface LedgerColumns {
    readonly table: TableState;
    readonly seats: readonly number[];
}

function ledgerRow({ seats, table }: LedgerColumns, record: RoundRecord, round: number): LedgerRow {
    const name = nameOf(table.players);
    const riichiCost = requireRiichiCost(table);
    return {
        cells: seats.map((seat) => {
            const delta = ledgerDelta(record, seat, riichiCost);
            return {
                dealer: seat === record.dealerSeat,
                mark: cellMark(record, seat),
                riichi: record.riichiSeats.includes(seat),
                text: cellText(record, seats, { delta, seat }),
                tone: tone(delta),
            };
        }),
        honba: record.honba,
        name: roundName(
            record.wind,
            roundInWind({ dealerSeat: record.dealerSeat, firstDealerSeat: table.firstDealerSeat }),
        ),
        outcome: outcomeName(record),
        round,
        summary: outcomeSummary(record, name),
    };
}

/**
 * The sticks left at the game's end: those the winner's score holds, else, where the rules award them to nobody, the
 * table's count with every column blank; null when none were left.
 */
function leftoverSticks(end: GameEndResult, seats: readonly number[]): LeftoverSticks | null {
    const paid = end.leftoverRiichiBonus;
    if (paid > 0) {
        return {
            awarded: true,
            cells: seats.map((seat) => (seat === end.winnerSeat ? formatDelta(paid) : "")),
            sticks: paid / RIICHI_STICK_VALUE,
        };
    }
    if (end.leftoverSticks === 0) {
        return null;
    }
    return { awarded: false, cells: seats.map(() => ""), sticks: end.leftoverSticks };
}

/**
 * The standings of a table whose game ended, read from `viewerSeat` (the live player's seat, the replay's bottom seat,
 * or none): the seats in placement order with their scores and uma/oka results as the server gave them, the ledger of
 * every round the table recorded, marked incomplete when that is not every round the server played as it played it,
 * and the leftover riichi sticks paid to the winner. Null before the game ends.
 */
export function standingsDisplay(
    table: TableState,
    viewerSeat: number | null,
): StandingsDisplay | null {
    const end = table.gameEndResult;
    if (table.phase !== "game_ended" || end === null) {
        return null;
    }
    const name = nameOf(table.players);
    const seats = end.standings.map((standing) => standing.seat);
    return {
        ledger: table.roundHistory.map((record, round) =>
            ledgerRow({ seats, table }, record, round),
        ),
        ledgerComplete: table.roundHistoryInStep && table.roundHistory.length === end.numRounds,
        leftover: leftoverSticks(end, seats),
        seats: end.standings.map((standing, index) => ({
            name: name(standing.seat),
            placement: PLACEMENTS[index] ?? `${index + 1}th`,
            result: formatResult(standing.finalScore),
            resultTone: tone(standing.finalScore),
            score: formatPoints(standing.score),
            seat: standing.seat,
            viewer: standing.seat === viewerSeat,
        })),
    };
}
