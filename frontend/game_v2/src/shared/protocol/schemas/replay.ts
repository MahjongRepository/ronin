import { z } from "zod/mini";

import { EVENT_TYPE, REPLAY_LINE_TYPE } from "@/shared/protocol/constants";
import { WIRE_KEY } from "@/shared/protocol/wire-keys";

import { seatControlReasonSchema, seatSchema } from "./common";
import { type ParsedServerMessage, parseRecordedMessage } from "./message";

const aiReplacementSchema = z.pipe(
    z.object({
        [WIRE_KEY.AI_PLAYER]: z.literal(1),
        [WIRE_KEY.SEAT_CONTROL_REASON]: seatControlReasonSchema,
        [WIRE_KEY.SEAT]: seatSchema,
        [WIRE_KEY.EVENT_TYPE]: z.literal(REPLAY_LINE_TYPE.SEAT_CONTROL),
    }),
    z.transform((raw) => ({
        reason: raw[WIRE_KEY.SEAT_CONTROL_REASON],
        seat: raw[WIRE_KEY.SEAT],
        type: "ai_replacement" as const,
    })),
);

const humanReturnSchema = z.pipe(
    z.object({
        [WIRE_KEY.AI_PLAYER]: z.literal(0),
        [WIRE_KEY.SEAT]: seatSchema,
        [WIRE_KEY.EVENT_TYPE]: z.literal(REPLAY_LINE_TYPE.SEAT_CONTROL),
    }),
    z.transform((raw) => ({
        seat: raw[WIRE_KEY.SEAT],
        type: "human_return" as const,
    })),
);

const viewingSettingsSchema = z.object({
    [WIRE_KEY.HAS_AKADORA]: z.boolean(),
    [WIRE_KEY.GAME_SETTINGS]: z.strictObject({
        id: z.int().check(z.minimum(1)),
        overrides: z.record(z.string(), z.unknown()),
    }),
    [WIRE_KEY.RNG_VERSION]: z.string(),
    [WIRE_KEY.SEED]: z.string().check(z.regex(/^[0-9a-f]{192}$/)),
});

export type AiReplacementLine = z.output<typeof aiReplacementSchema>;
export type HumanReturnLine = z.output<typeof humanReturnSchema>;
export type SeatControlLine = AiReplacementLine | HumanReturnLine;

export type ReplayLine = ParsedServerMessage | SeatControlLine;

export type ReplayLineParseResult = [Error, null] | [null, ReplayLine];

/** Dispatch on `WIRE_KEY.AI_PLAYER` by hand: Zod's discriminatedUnion does not work with `.transform()`. */
function parseSeatControl(raw: Record<string, unknown>): SeatControlLine {
    const { [WIRE_KEY.AI_PLAYER]: ai } = raw;
    switch (ai) {
        case 1: {
            return aiReplacementSchema.parse(raw);
        }
        case 0: {
            return humanReturnSchema.parse(raw);
        }
        default: {
            throw new Error(`Unknown seat control: AI_PLAYER=${String(ai)}`);
        }
    }
}

/** A recorded message as the replay needs it: a deal records every seat's hand, since a replay shows them all. */
function recordedMessage(raw: Record<string, unknown>): ReplayLineParseResult {
    const parsed = parseRecordedMessage(raw);
    const [, message] = parsed;
    if (message?.type === "round_started" && message.players.some(({ tiles }) => tiles === null)) {
        return [
            new Error("Failed to parse deal EVENT_TYPE=9: it does not record every seat's hand"),
            null,
        ];
    }
    return parsed;
}

/** Parse one replay event line: a game event, or a replay-only line the live socket never sends. */
export function parseReplayLine(raw: Record<string, unknown>): ReplayLineParseResult {
    try {
        switch (raw[WIRE_KEY.EVENT_TYPE]) {
            case REPLAY_LINE_TYPE.SEAT_CONTROL: {
                return [null, parseSeatControl(raw)];
            }
            case EVENT_TYPE.GAME_STARTED: {
                const viewing = viewingSettingsSchema.parse(raw);
                const parsed = recordedMessage(raw);
                const [error, message] = parsed;
                return error === null && message.type === "game_started"
                    ? [null, { ...message, hasAkadora: viewing[WIRE_KEY.HAS_AKADORA] }]
                    : parsed;
            }
            default: {
                return recordedMessage(raw);
            }
        }
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return [
            new Error(
                `Failed to parse replay line EVENT_TYPE=${raw[WIRE_KEY.EVENT_TYPE]}: ${message}`,
                {
                    cause: error,
                },
            ),
            null,
        ];
    }
}
