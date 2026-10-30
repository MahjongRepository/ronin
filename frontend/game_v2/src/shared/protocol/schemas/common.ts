import { z } from "zod/mini";

import { NUM_PLAYERS, SEAT_CONTROL_REASON, WIRE_SCORE_DIVISOR } from "@/shared/protocol/constants";
import { MAX_MELD_COMPACT, meldCompactCaller } from "@/shared/protocol/decoders/meld";

// Tile ID: integer 0-135 (136-format tile encoding)
export const tileIdSchema = z.int().check(z.gte(0), z.lte(135));

export const tileTypeSchema = z.int().check(z.gte(0), z.lte(33));

// Seat: integer 0-3 (4-player game)
export const seatSchema = z.int().check(z.gte(0), z.lte(3));

export const waitIdSchema = z.int().check(z.gte(0));

/** A meld in its compact (IMME) value, which `decodeMeldCompact` unpacks: only a value it can decode parses. */
export const compactMeldSchema = z.int().check(z.gte(0), z.lte(MAX_MELD_COMPACT));

/** Whether every compact meld of a seat's list was called by that seat, as the server lists a seat's own melds. */
export function calledBy(melds: readonly number[], seat: number): boolean {
    return melds.every((meld) => meldCompactCaller(meld) === seat);
}

/** Whether a per-seat list names each of the four seats once, in seat order, as the server builds every such list. */
export function coversEverySeat(entries: readonly { readonly seat: number }[]): boolean {
    return entries.length === NUM_PLAYERS && entries.every((entry, index) => entry.seat === index);
}

export const seatControlReasonSchema = z.union([
    z.literal(SEAT_CONTROL_REASON.LEFT),
    z.literal(SEAT_CONTROL_REASON.ABSENT),
]);

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
// Transforms wire-format `ai` integer to boolean and renames aliases to camelCase.
export const gamePlayerInfoSchema = z.pipe(
    z.object({
        ai: z.int(),
        nm: z.string(),
        s: seatSchema,
        sr: z.optional(seatControlReasonSchema),
    }),
    z.transform((raw) => ({
        aiStandIn: raw.sr ?? null,
        isAiPlayer: raw.ai !== 0,
        name: raw.nm,
        seat: raw.s,
    })),
);

export const timerSettingsSchema = z.pipe(
    z.object({
        bk: secondsSchema,
        gp: secondsSchema,
        mb: secondsSchema,
        md: secondsSchema,
        ra: secondsSchema,
        rb: secondsSchema,
        tb: secondsSchema,
    }),
    z.transform((raw) => ({
        bankSeconds: raw.bk,
        baseTurnSeconds: raw.tb,
        gameStartPauseSeconds: raw.gp,
        maxBankSeconds: raw.mb,
        meldDecisionSeconds: raw.md,
        roundAdvanceTimeoutSeconds: raw.ra,
        roundBonusSeconds: raw.rb,
    })),
);
