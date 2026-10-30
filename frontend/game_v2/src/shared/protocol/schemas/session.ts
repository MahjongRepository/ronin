import { z } from "zod/mini";

import { SESSION_MESSAGE_TYPE } from "@/shared/protocol/constants";

import { seatControlReasonSchema, seatSchema } from "./common";

// --- Session Error ---

const sessionErrorSchema = z.pipe(
    z.object({
        code: z.string(),
        message: z.string(),
        type: z.literal(SESSION_MESSAGE_TYPE.ERROR),
    }),
    z.transform((raw) => ({
        code: raw.code,
        message: raw.message,
        type: "session_error" as const,
    })),
);

/**
 * A seat changing hands, live as a replay's seat control line records it, so it parses into the same shapes: an AI
 * player stands in for the seat's human (`r` says why), or without `r`, the human takes it back.
 */
const seatControlSchema = z.pipe(
    z.object({
        r: z.optional(seatControlReasonSchema),
        s: seatSchema,
        type: z.literal(SESSION_MESSAGE_TYPE.SEAT_CONTROL),
    }),
    z.transform((raw) =>
        raw.r === undefined
            ? { seat: raw.s, type: "human_return" as const }
            : { reason: raw.r, seat: raw.s, type: "ai_replacement" as const },
    ),
);

// --- Dispatch ---

export type SessionErrorMessage = z.output<typeof sessionErrorSchema>;
export type SeatControlMessage = z.output<typeof seatControlSchema>;

export type SessionMessage = SessionErrorMessage | SeatControlMessage;

export function parseSessionMessage(raw: Record<string, unknown>): SessionMessage {
    const { type } = raw;
    switch (type) {
        case SESSION_MESSAGE_TYPE.ERROR: {
            return sessionErrorSchema.parse(raw);
        }
        case SESSION_MESSAGE_TYPE.SEAT_CONTROL: {
            return seatControlSchema.parse(raw);
        }
        default: {
            throw new Error(`Unknown session message type: type=${String(type)}`);
        }
    }
}
