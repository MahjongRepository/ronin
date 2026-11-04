import { z } from "zod/mini";

import { CALL_TYPE, EVENT_TYPE, KAN_TYPE, MELD_CALL_TYPE } from "@/shared/protocol/constants";
import { WIRE_KEY } from "@/shared/protocol/wire-keys";

import { seatSchema, secondsSchema, tileIdSchema, waitIdSchema } from "./common";

/** One offered call: a chi with the pairs it may be called with, a nonempty list; a pon or an open kan with none. */
const availableCallSchema = z.union([
    z.pipe(
        z.object({
            [WIRE_KEY.CALL_TYPE]: z.literal(MELD_CALL_TYPE.CHI),
            [WIRE_KEY.CALL_OPTIONS]: z
                .array(z.tuple([tileIdSchema, tileIdSchema]))
                .check(z.minLength(1)),
        }),
        z.transform((raw) => ({
            callType: raw[WIRE_KEY.CALL_TYPE],
            options: raw[WIRE_KEY.CALL_OPTIONS],
        })),
    ),
    z.pipe(
        z.object({
            [WIRE_KEY.CALL_TYPE]: z.union([
                z.literal(MELD_CALL_TYPE.PON),
                z.literal(MELD_CALL_TYPE.OPEN_KAN),
            ]),
        }),
        z.transform((raw) => ({ callType: raw[WIRE_KEY.CALL_TYPE] })),
    ),
]);

const ronPromptSchema = z.pipe(
    z.object({
        [WIRE_KEY.AVAILABLE_CALLS]: z.optional(z.array(availableCallSchema)),
        [WIRE_KEY.BANK_SECONDS]: z.optional(secondsSchema),
        [WIRE_KEY.CALL_TYPE]: z.literal(CALL_TYPE.RON),
        [WIRE_KEY.CALLER_SEAT]: seatSchema,
        [WIRE_KEY.WAIT_ELAPSED]: z.optional(secondsSchema),
        [WIRE_KEY.FROM_SEAT]: seatSchema,
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.CALL_PROMPT),
        [WIRE_KEY.TILE_ID]: tileIdSchema,
        [WIRE_KEY.WAIT_ID]: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        availableCalls: raw[WIRE_KEY.AVAILABLE_CALLS] ?? [],
        bankSeconds: raw[WIRE_KEY.BANK_SECONDS] ?? null,
        callType: CALL_TYPE.RON as typeof CALL_TYPE.RON,
        callerSeat: raw[WIRE_KEY.CALLER_SEAT],
        elapsedSeconds: raw[WIRE_KEY.WAIT_ELAPSED] ?? null,
        fromSeat: raw[WIRE_KEY.FROM_SEAT],
        tileId: raw[WIRE_KEY.TILE_ID],
        type: "call_prompt" as const,
        waitId: raw[WIRE_KEY.WAIT_ID] ?? null,
    })),
);

/** A chankan prompt names the kan it offers to rob: an added kan, or the closed kan kokushi musou may rob. */
const chankanPromptSchema = z.pipe(
    z.object({
        [WIRE_KEY.BANK_SECONDS]: z.optional(secondsSchema),
        [WIRE_KEY.CALL_TYPE]: z.literal(CALL_TYPE.CHANKAN),
        [WIRE_KEY.CALLER_SEAT]: seatSchema,
        [WIRE_KEY.WAIT_ELAPSED]: z.optional(secondsSchema),
        [WIRE_KEY.FROM_SEAT]: seatSchema,
        [WIRE_KEY.KAN_TYPE]: z.union([z.literal(KAN_TYPE.ADDED), z.literal(KAN_TYPE.CLOSED)]),
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.CALL_PROMPT),
        [WIRE_KEY.TILE_ID]: tileIdSchema,
        [WIRE_KEY.WAIT_ID]: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        bankSeconds: raw[WIRE_KEY.BANK_SECONDS] ?? null,
        callType: CALL_TYPE.CHANKAN as typeof CALL_TYPE.CHANKAN,
        callerSeat: raw[WIRE_KEY.CALLER_SEAT],
        elapsedSeconds: raw[WIRE_KEY.WAIT_ELAPSED] ?? null,
        fromSeat: raw[WIRE_KEY.FROM_SEAT],
        kanType: raw[WIRE_KEY.KAN_TYPE],
        tileId: raw[WIRE_KEY.TILE_ID],
        type: "call_prompt" as const,
        waitId: raw[WIRE_KEY.WAIT_ID] ?? null,
    })),
);

const meldPromptSchema = z.pipe(
    z.object({
        [WIRE_KEY.AVAILABLE_CALLS]: z.array(availableCallSchema).check(z.minLength(1)),
        [WIRE_KEY.BANK_SECONDS]: z.optional(secondsSchema),
        [WIRE_KEY.CALL_TYPE]: z.literal(CALL_TYPE.MELD),
        [WIRE_KEY.CALLER_SEAT]: seatSchema,
        [WIRE_KEY.WAIT_ELAPSED]: z.optional(secondsSchema),
        [WIRE_KEY.FROM_SEAT]: seatSchema,
        [WIRE_KEY.EVENT_TYPE]: z.literal(EVENT_TYPE.CALL_PROMPT),
        [WIRE_KEY.TILE_ID]: tileIdSchema,
        [WIRE_KEY.WAIT_ID]: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        availableCalls: raw[WIRE_KEY.AVAILABLE_CALLS],
        bankSeconds: raw[WIRE_KEY.BANK_SECONDS] ?? null,
        callType: CALL_TYPE.MELD as typeof CALL_TYPE.MELD,
        callerSeat: raw[WIRE_KEY.CALLER_SEAT],
        elapsedSeconds: raw[WIRE_KEY.WAIT_ELAPSED] ?? null,
        fromSeat: raw[WIRE_KEY.FROM_SEAT],
        tileId: raw[WIRE_KEY.TILE_ID],
        type: "call_prompt" as const,
        waitId: raw[WIRE_KEY.WAIT_ID] ?? null,
    })),
);

// --- Dispatch ---

export type RonPromptEvent = z.output<typeof ronPromptSchema>;
export type ChankanPromptEvent = z.output<typeof chankanPromptSchema>;
export type MeldPromptEvent = z.output<typeof meldPromptSchema>;
export type CallPromptEvent = RonPromptEvent | ChankanPromptEvent | MeldPromptEvent;

/** Dispatch on `WIRE_KEY.CALL_TYPE` by hand: Zod's discriminatedUnion does not work with `.transform()`. */
export function parseCallPrompt(raw: Record<string, unknown>): CallPromptEvent {
    const { [WIRE_KEY.CALL_TYPE]: clt } = raw;
    switch (clt) {
        case CALL_TYPE.RON: {
            return ronPromptSchema.parse(raw);
        }
        case CALL_TYPE.MELD: {
            return meldPromptSchema.parse(raw);
        }
        case CALL_TYPE.CHANKAN: {
            return chankanPromptSchema.parse(raw);
        }
        default: {
            throw new Error(`Unknown call prompt type: CALL_TYPE=${String(clt)}`);
        }
    }
}
