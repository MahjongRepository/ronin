import { z } from "zod";

import { WIRE_SCORE_DIVISOR } from "@/shared/protocol/constants";

// Tile ID: integer 0-135 (136-format tile encoding)
export const tileIdSchema = z.number().int().min(0).max(135);

export const tileTypeSchema = z.number().int().min(0).max(33);

// Seat: integer 0-3 (4-player game)
export const seatSchema = z.number().int().min(0).max(3);

export const waitIdSchema = z.number().int().min(0);

export const secondsSchema = z.number().min(0);

export const wireScoreSchema = z.number().transform((value) => value * WIRE_SCORE_DIVISOR);

// Wire score map: Record of string-keyed scores divided by WIRE_SCORE_DIVISOR.
// Transforms wire values (e.g. 250) back to real scores (e.g. 25000).
// Uses plain objects (not Map) so JSON.stringify works correctly.
export const wireScoreMapSchema = z
    .record(z.string(), z.number())
    .transform((rec) =>
        Object.fromEntries(
            Object.entries(rec).map(([key, value]) => [key, value * WIRE_SCORE_DIVISOR]),
        ),
    );

// Player info: shared between game_started and game_reconnected events.
// Transforms wire-format `ai` integer to boolean and renames aliases to camelCase.
export const gamePlayerInfoSchema = z
    .object({
        ai: z.number().int(),
        nm: z.string(),
        s: seatSchema,
    })
    .transform((raw) => ({
        isAiPlayer: raw.ai !== 0,
        name: raw.nm,
        seat: raw.s,
    }));

export const timerSettingsSchema = z
    .object({
        bk: secondsSchema,
        gp: secondsSchema,
        mb: secondsSchema,
        md: secondsSchema,
        ra: secondsSchema,
        rb: secondsSchema,
        tb: secondsSchema,
    })
    .transform((raw) => ({
        bankSeconds: raw.bk,
        baseTurnSeconds: raw.tb,
        gameStartPauseSeconds: raw.gp,
        maxBankSeconds: raw.mb,
        meldDecisionSeconds: raw.md,
        roundAdvanceTimeoutSeconds: raw.ra,
        roundBonusSeconds: raw.rb,
    }));
