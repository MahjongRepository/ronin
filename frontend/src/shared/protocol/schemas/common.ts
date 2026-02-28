// Shared Zod schema helpers for wire protocol parsing.

import { z } from "zod";

import { WIRE_SCORE_DIVISOR } from "../constants";

// Tile ID: integer 0-135 (136-format tile encoding)
export const tileIdSchema = z.number().int().min(0).max(135);

// Seat: integer 0-3 (4-player game)
export const seatSchema = z.number().int().min(0).max(3);

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
