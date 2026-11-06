import { z } from "zod/mini";

import {
    GAME_TYPE,
    NUM_PLAYERS,
    SEAT_CONTROL_REASON,
    WIRE_SCORE_DIVISOR,
} from "@/shared/protocol/constants";
import {
    type DecodedMeld,
    MAX_MELD_COMPACT,
    decodeMeldCompact,
} from "@/shared/protocol/decoders/meld";
import { WIRE_KEY } from "@/shared/protocol/wire-keys";

// Tile ID: integer 0-135 (136-format tile encoding)
export const tileIdSchema = z.int().check(z.gte(0), z.lte(135));

export const tileTypeSchema = z.int().check(z.gte(0), z.lte(33));

// Seat: integer 0-3 (4-player game)
export const seatSchema = z.int().check(z.gte(0), z.lte(3));

export const waitIdSchema = z.int().check(z.gte(0));

export const gameTypeSchema = z.union([
    z.literal(GAME_TYPE.HANCHAN),
    z.literal(GAME_TYPE.TONPUSEN),
]);

/** The live wall's tiles left, as the server counts them. */
export const tilesRemainingSchema = z.int().check(z.gte(0));

/** A round's number within its wind, from 1 ("East 1"). */
export const roundInWindSchema = z.int().check(z.gte(1));

/** A meld in its compact (IMME) value, decoded as it parses: only a value the decoder can unpack parses. */
export const compactMeldSchema = z.pipe(
    z.int().check(z.gte(0), z.lte(MAX_MELD_COMPACT)),
    z.transform(decodeMeldCompact),
);

/** Whether every meld of a seat's list was called by that seat, as the server lists a seat's own melds. */
export function calledBy(melds: readonly DecodedMeld[], seat: number): boolean {
    return melds.every((meld) => meld.callerSeat === seat);
}

/** Whether a per-seat list names each of the four seats once, in seat order, as the server builds every such list. */
export function coversEverySeat(entries: readonly { readonly seat: number }[]): boolean {
    return entries.length === NUM_PLAYERS && entries.every((entry, index) => entry.seat === index);
}

/** Whether a list names no seat twice, in whatever order (a game end's ranked standings, a double ron's winners). */
export function namesDistinctSeats(seats: readonly number[]): boolean {
    return new Set(seats).size === seats.length;
}

export const seatControlReasonSchema = z.union([
    z.literal(SEAT_CONTROL_REASON.LEFT),
    z.literal(SEAT_CONTROL_REASON.ABSENT),
]);

/** A discard as it lies in its river (`WIRE_KEY.DISCARDS` of a snapshot's seat, of a nagashi mangan's river). */
export const discardInfoSchema = z.pipe(
    z.object({
        [WIRE_KEY.RIICHI_DISCARD]: z.optional(z.boolean()),
        [WIRE_KEY.TSUMOGIRI]: z.optional(z.boolean()),
        [WIRE_KEY.TILE_ID]: tileIdSchema,
    }),
    z.transform((raw) => ({
        isRiichiDiscard: raw[WIRE_KEY.RIICHI_DISCARD] ?? false,
        isTsumogiri: raw[WIRE_KEY.TSUMOGIRI] ?? false,
        tileId: raw[WIRE_KEY.TILE_ID],
    })),
);

export const secondsSchema = z.number().check(z.gte(0));

export const wireScoreSchema = z.pipe(
    z.number(),
    z.transform((value) => value * WIRE_SCORE_DIVISOR),
);

/** A game setting's amount in wire score units: a whole, nonnegative number of them, as the server validates it. */
export const wireSettingAmountSchema = z.pipe(
    z.int().check(z.gte(0)),
    z.transform((value) => value * WIRE_SCORE_DIVISOR),
);

const SEAT_KEYS = Array.from({ length: NUM_PLAYERS }, (_seat, index) => String(index));

/** Whether a score map names every seat once and nothing else, as every map the server builds does. */
function namesEverySeat(rec: Readonly<Record<string, number>>): boolean {
    const keys = Object.keys(rec);
    return keys.length === NUM_PLAYERS && SEAT_KEYS.every((key) => key in rec);
}

/**
 * A score per seat keyed by the seat, wire values (250) back to real scores (25000), as a plain object so it
 * serializes. The server always sends every seat's, a zero included, so a map missing one does not parse rather than
 * reading the missing seat as zero.
 */
export const wireScoreMapSchema = z.pipe(
    z
        .record(z.string(), z.number())
        .check(z.refine(namesEverySeat, { message: "a score map does not name every seat" })),
    z.transform((rec) =>
        Object.fromEntries(
            Object.entries(rec).map(([key, value]) => [key, value * WIRE_SCORE_DIVISOR]),
        ),
    ),
);

// Player info: shared between game_started and game_reconnected events.
export const gamePlayerInfoSchema = z.pipe(
    z.object({
        [WIRE_KEY.AI_PLAYER]: z.int(),
        [WIRE_KEY.NAME]: z.string(),
        [WIRE_KEY.SEAT]: seatSchema,
        [WIRE_KEY.STAND_IN_REASON]: z.optional(seatControlReasonSchema),
    }),
    z.transform((raw) => ({
        aiStandIn: raw[WIRE_KEY.STAND_IN_REASON] ?? null,
        isAiPlayer: raw[WIRE_KEY.AI_PLAYER] !== 0,
        name: raw[WIRE_KEY.NAME],
        seat: raw[WIRE_KEY.SEAT],
    })),
);

export const timerSettingsSchema = z.pipe(
    z.object({
        [WIRE_KEY.BANK_SECONDS]: secondsSchema,
        [WIRE_KEY.GAME_START_CONFIRM]: secondsSchema,
        [WIRE_KEY.MAX_BANK_SECONDS]: secondsSchema,
        [WIRE_KEY.ROUND_ADVANCE_TIMEOUT]: secondsSchema,
        [WIRE_KEY.BASE_TURN_SECONDS]: secondsSchema,
    }),
    z.transform((raw) => ({
        bankSeconds: raw[WIRE_KEY.BANK_SECONDS],
        baseTurnSeconds: raw[WIRE_KEY.BASE_TURN_SECONDS],
        gameStartConfirmSeconds: raw[WIRE_KEY.GAME_START_CONFIRM],
        maxBankSeconds: raw[WIRE_KEY.MAX_BANK_SECONDS],
        roundAdvanceTimeoutSeconds: raw[WIRE_KEY.ROUND_ADVANCE_TIMEOUT],
    })),
);
