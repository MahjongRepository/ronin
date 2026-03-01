// Zod schemas for call prompt event variants (t=3).
// Three variants based on `clt` field: ron (0), meld (1), chankan (2).
// Manual dispatch via parseCallPrompt() since Zod discriminatedUnion
// doesn't work with .transform().

import { z } from "zod";

import { CALL_TYPE, EVENT_TYPE, MELD_CALL_TYPE } from "@/shared/protocol/constants";

import { seatSchema, tileIdSchema } from "./common";

// --- Available call option (inside meld prompt `ac` array) ---

const meldCallTypeSchema = z.union([
    z.literal(MELD_CALL_TYPE.PON),
    z.literal(MELD_CALL_TYPE.CHI),
    z.literal(MELD_CALL_TYPE.OPEN_KAN),
]);

const availableCallSchema = z
    .object({
        clt: meldCallTypeSchema,
        opt: z
            .array(z.tuple([tileIdSchema, tileIdSchema]))
            .nullable()
            .optional(),
    })
    .transform((raw) => ({
        callType: raw.clt,
        options: raw.opt ?? null,
    }));

// --- Ron prompt (clt=0) ---

const ronPromptSchema = z
    .object({
        clt: z.literal(CALL_TYPE.RON),
        cs: seatSchema,
        frs: seatSchema,
        t: z.literal(EVENT_TYPE.CALL_PROMPT),
        ti: tileIdSchema,
    })
    .transform((raw) => ({
        callType: CALL_TYPE.RON as typeof CALL_TYPE.RON,
        callerSeat: raw.cs,
        fromSeat: raw.frs,
        tileId: raw.ti,
        type: "call_prompt" as const,
    }));

// --- Chankan prompt (clt=2) ---

const chankanPromptSchema = z
    .object({
        clt: z.literal(CALL_TYPE.CHANKAN),
        cs: seatSchema,
        frs: seatSchema,
        t: z.literal(EVENT_TYPE.CALL_PROMPT),
        ti: tileIdSchema,
    })
    .transform((raw) => ({
        callType: CALL_TYPE.CHANKAN as typeof CALL_TYPE.CHANKAN,
        callerSeat: raw.cs,
        fromSeat: raw.frs,
        tileId: raw.ti,
        type: "call_prompt" as const,
    }));

// --- Meld prompt (clt=1) ---

const meldPromptSchema = z
    .object({
        ac: z.array(availableCallSchema),
        clt: z.literal(CALL_TYPE.MELD),
        cs: seatSchema,
        frs: seatSchema,
        t: z.literal(EVENT_TYPE.CALL_PROMPT),
        ti: tileIdSchema,
    })
    .transform((raw) => ({
        availableCalls: raw.ac,
        callType: CALL_TYPE.MELD as typeof CALL_TYPE.MELD,
        callerSeat: raw.cs,
        fromSeat: raw.frs,
        tileId: raw.ti,
        type: "call_prompt" as const,
    }));

// --- Dispatch ---

export type RonPromptEvent = z.output<typeof ronPromptSchema>;
export type ChankanPromptEvent = z.output<typeof chankanPromptSchema>;
export type MeldPromptEvent = z.output<typeof meldPromptSchema>;
export type CallPromptEvent = RonPromptEvent | ChankanPromptEvent | MeldPromptEvent;

export function parseCallPrompt(raw: Record<string, unknown>): CallPromptEvent {
    const { clt } = raw;
    switch (clt) {
        case CALL_TYPE.RON:
            return ronPromptSchema.parse(raw);
        case CALL_TYPE.MELD:
            return meldPromptSchema.parse(raw);
        case CALL_TYPE.CHANKAN:
            return chankanPromptSchema.parse(raw);
        default:
            throw new Error(`Unknown call prompt type: clt=${String(clt)}`);
    }
}
