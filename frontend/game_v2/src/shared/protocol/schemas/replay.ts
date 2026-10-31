import { z } from "zod/mini";

import { EVENT_TYPE, REPLAY_LINE_TYPE, WIRE_SCORE_DIVISOR } from "@/shared/protocol/constants";

import { seatControlReasonSchema, seatSchema } from "./common";
import { type ParsedServerMessage, parseRecordedMessage } from "./message";

const aiReplacementSchema = z.pipe(
    z.object({
        ai: z.literal(1),
        r: seatControlReasonSchema,
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

const replaySettingsSchema = z.object({ riichi_cost: z.int(), riichi_stick_value: z.int() });

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

/**
 * The replay's game start as the live one: its riichi cost (`rc`) and stick value (`rsv`) from the settings it records
 * (`gs`), which every replay file carries in place of the live fields.
 */
function withRecordedRiichiSettings(raw: Record<string, unknown>): Record<string, unknown> {
    const settings = replaySettingsSchema.parse(raw.gs);
    return {
        ...raw,
        rc: settings.riichi_cost / WIRE_SCORE_DIVISOR,
        rsv: settings.riichi_stick_value / WIRE_SCORE_DIVISOR,
    };
}

/** A recorded message as the replay needs it: a deal records every seat's hand, since a replay shows them all. */
function recordedMessage(raw: Record<string, unknown>): ReplayLineParseResult {
    const parsed = parseRecordedMessage(raw);
    const [, message] = parsed;
    if (message?.type === "round_started" && message.players.some(({ tiles }) => tiles === null)) {
        return [new Error("Failed to parse deal t=9: it does not record every seat's hand"), null];
    }
    return parsed;
}

/** Parse one replay event line: a game event, or a replay-only line the live socket never sends. */
export function parseReplayLine(raw: Record<string, unknown>): ReplayLineParseResult {
    try {
        switch (raw.t) {
            case REPLAY_LINE_TYPE.SEAT_CONTROL: {
                return [null, parseSeatControl(raw)];
            }
            case EVENT_TYPE.GAME_STARTED: {
                return recordedMessage(withRecordedRiichiSettings(raw));
            }
            default: {
                return recordedMessage(raw);
            }
        }
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return [
            new Error(`Failed to parse replay line t=${raw.t}: ${message}`, { cause: error }),
            null,
        ];
    }
}
