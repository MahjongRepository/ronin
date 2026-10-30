import { z } from "zod/mini";

import { SEAT_CONTROL_REASON, WIRE_SCORE_DIVISOR } from "@/shared/protocol/constants";

// Tile ID: integer 0-135 (136-format tile encoding)
export const tileIdSchema = z.int().check(z.gte(0), z.lte(135));

export const tileTypeSchema = z.int().check(z.gte(0), z.lte(33));

// Seat: integer 0-3 (4-player game)
export const seatSchema = z.int().check(z.gte(0), z.lte(3));

export const waitIdSchema = z.int().check(z.gte(0));

export const seatControlReasonSchema = z.union([
    z.literal(SEAT_CONTROL_REASON.LEFT),
    z.literal(SEAT_CONTROL_REASON.ABSENT),
]);

export const secondsSchema = z.number().check(z.gte(0));

export const wireScoreSchema = z.pipe(
    z.number(),
    z.transform((value) => value * WIRE_SCORE_DIVISOR),
);

// Wire score map: Record of string-keyed scores divided by WIRE_SCORE_DIVISOR.
// Transforms wire values (e.g. 250) back to real scores (e.g. 25000).
// Uses plain objects (not Map) so JSON.stringify works correctly.
export const wireScoreMapSchema = z.pipe(
    z.record(z.string(), z.number()),
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
