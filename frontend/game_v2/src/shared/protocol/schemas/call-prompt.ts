import { z } from "zod/mini";

import { CALL_TYPE, EVENT_TYPE, KAN_TYPE, MELD_CALL_TYPE } from "@/shared/protocol/constants";

import { seatSchema, secondsSchema, tileIdSchema, waitIdSchema } from "./common";

// --- Available call option (inside meld prompt `ac` array) ---

/** One offered call: a chi with the pairs it may be called with, a nonempty list; a pon or an open kan with none. */
const availableCallSchema = z.union([
    z.pipe(
        z.object({
            clt: z.literal(MELD_CALL_TYPE.CHI),
            opt: z.array(z.tuple([tileIdSchema, tileIdSchema])).check(z.minLength(1)),
        }),
        z.transform((raw) => ({ callType: raw.clt, options: raw.opt })),
    ),
    z.pipe(
        z.object({
            clt: z.union([z.literal(MELD_CALL_TYPE.PON), z.literal(MELD_CALL_TYPE.OPEN_KAN)]),
        }),
        z.transform((raw) => ({ callType: raw.clt })),
    ),
]);

// --- Ron prompt (clt=0) ---

const ronPromptSchema = z.pipe(
    z.object({
        ac: z.optional(z.array(availableCallSchema)),
        clt: z.literal(CALL_TYPE.RON),
        cs: seatSchema,
        el: z.optional(secondsSchema),
        frs: seatSchema,
        t: z.literal(EVENT_TYPE.CALL_PROMPT),
        ti: tileIdSchema,
        wi: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        availableCalls: raw.ac ?? [],
        callType: CALL_TYPE.RON as typeof CALL_TYPE.RON,
        callerSeat: raw.cs,
        elapsedSeconds: raw.el ?? null,
        fromSeat: raw.frs,
        tileId: raw.ti,
        type: "call_prompt" as const,
        waitId: raw.wi ?? null,
    })),
);

// --- Chankan prompt (clt=2) ---

/** A chankan prompt names the kan it offers to rob: an added kan, or the closed kan kokushi musou may rob. */
const chankanPromptSchema = z.pipe(
    z.object({
        clt: z.literal(CALL_TYPE.CHANKAN),
        cs: seatSchema,
        el: z.optional(secondsSchema),
        frs: seatSchema,
        kty: z.union([z.literal(KAN_TYPE.ADDED), z.literal(KAN_TYPE.CLOSED)]),
        t: z.literal(EVENT_TYPE.CALL_PROMPT),
        ti: tileIdSchema,
        wi: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        callType: CALL_TYPE.CHANKAN as typeof CALL_TYPE.CHANKAN,
        callerSeat: raw.cs,
        elapsedSeconds: raw.el ?? null,
        fromSeat: raw.frs,
        kanType: raw.kty,
        tileId: raw.ti,
        type: "call_prompt" as const,
        waitId: raw.wi ?? null,
    })),
);

// --- Meld prompt (clt=1) ---

const meldPromptSchema = z.pipe(
    z.object({
        ac: z.array(availableCallSchema).check(z.minLength(1)),
        clt: z.literal(CALL_TYPE.MELD),
        cs: seatSchema,
        el: z.optional(secondsSchema),
        frs: seatSchema,
        t: z.literal(EVENT_TYPE.CALL_PROMPT),
        ti: tileIdSchema,
        wi: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        availableCalls: raw.ac,
        callType: CALL_TYPE.MELD as typeof CALL_TYPE.MELD,
        callerSeat: raw.cs,
        elapsedSeconds: raw.el ?? null,
        fromSeat: raw.frs,
        tileId: raw.ti,
        type: "call_prompt" as const,
        waitId: raw.wi ?? null,
    })),
);

// --- Dispatch ---

export type RonPromptEvent = z.output<typeof ronPromptSchema>;
export type ChankanPromptEvent = z.output<typeof chankanPromptSchema>;
export type MeldPromptEvent = z.output<typeof meldPromptSchema>;
export type CallPromptEvent = RonPromptEvent | ChankanPromptEvent | MeldPromptEvent;

/** Dispatch on `clt` by hand: Zod's discriminatedUnion does not work with `.transform()`. */
export function parseCallPrompt(raw: Record<string, unknown>): CallPromptEvent {
    const { clt } = raw;
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
            throw new Error(`Unknown call prompt type: clt=${String(clt)}`);
        }
    }
}
