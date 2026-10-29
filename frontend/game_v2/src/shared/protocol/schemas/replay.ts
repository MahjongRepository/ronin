import { z } from "zod/mini";

import { REPLAY_LINE_TYPE, SEAT_CONTROL_REASON } from "@/shared/protocol/constants";

import { seatSchema } from "./common";
import { type ParsedServerMessage, parseServerMessage } from "./message";

const aiReplacementSchema = z.pipe(
    z.object({
        ai: z.literal(1),
        r: z.union([z.literal(SEAT_CONTROL_REASON.LEFT), z.literal(SEAT_CONTROL_REASON.ABSENT)]),
        s: seatSchema,
        t: z.literal(REPLAY_LINE_TYPE.SEAT_CONTROL),
    }),
    z.transform((raw) => ({
        reason: raw.r,
        seat: raw.s,
        type: "ai_replacement" as const,
    })),
);

const humanReturnSchema = z.pipe(
    z.object({
        ai: z.literal(0),
        s: seatSchema,
        t: z.literal(REPLAY_LINE_TYPE.SEAT_CONTROL),
    }),
    z.transform((raw) => ({
        seat: raw.s,
        type: "human_return" as const,
    })),
);

export type AiReplacementLine = z.output<typeof aiReplacementSchema>;
export type HumanReturnLine = z.output<typeof humanReturnSchema>;
export type SeatControlLine = AiReplacementLine | HumanReturnLine;

export type ReplayLine = ParsedServerMessage | SeatControlLine;

export type ReplayLineParseResult = [Error, null] | [null, ReplayLine];

/** Dispatch on `ai` by hand: Zod's discriminatedUnion does not work with `.transform()`. */
function parseSeatControl(raw: Record<string, unknown>): SeatControlLine {
    const { ai } = raw;
    switch (ai) {
        case 1: {
            return aiReplacementSchema.parse(raw);
        }
        case 0: {
            return humanReturnSchema.parse(raw);
        }
        default: {
            throw new Error(`Unknown seat control: ai=${String(ai)}`);
        }
    }
}

/** Parse one replay event line: a game event, or a replay-only line the live socket never sends. */
export function parseReplayLine(raw: Record<string, unknown>): ReplayLineParseResult {
    if (raw.t !== REPLAY_LINE_TYPE.SEAT_CONTROL) {
        return parseServerMessage(raw);
    }
    try {
        return [null, parseSeatControl(raw)];
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return [
            new Error(`Failed to parse replay line t=${raw.t}: ${message}`, { cause: error }),
            null,
        ];
    }
}
