import { z } from "zod/mini";

import { SESSION_MESSAGE_TYPE } from "@/shared/protocol/constants";
import { WIRE_KEY } from "@/shared/protocol/wire-keys";

import { seatControlReasonSchema, seatSchema, secondsSchema, waitIdSchema } from "./common";

// --- Session Error ---

/** A session error; a rate limit names the wait id the refused game action echoed, when it had a readable one. */
const sessionErrorSchema = z.pipe(
    z.object({
        [WIRE_KEY.SESSION_ERROR_CODE]: z.string(),
        [WIRE_KEY.SESSION_ERROR_MESSAGE]: z.string(),
        [WIRE_KEY.SESSION_TYPE]: z.literal(SESSION_MESSAGE_TYPE.ERROR),
        [WIRE_KEY.WAIT_ID]: z.optional(waitIdSchema),
    }),
    z.transform((raw) => ({
        code: raw[WIRE_KEY.SESSION_ERROR_CODE],
        message: raw[WIRE_KEY.SESSION_ERROR_MESSAGE],
        type: "session_error" as const,
        waitId: raw[WIRE_KEY.WAIT_ID] ?? null,
    })),
);

/**
 * The server's answer to an accepted JOIN_GAME: the connection holds the seat, ahead of anything the game sends it,
 * and the pending game waits for its players at most `WIRE_KEY.PENDING_GAME_TIMEOUT` seconds before it starts.
 */
const gameJoinedSchema = z.pipe(
    z.object({
        [WIRE_KEY.PENDING_GAME_TIMEOUT]: secondsSchema,
        [WIRE_KEY.SESSION_TYPE]: z.literal(SESSION_MESSAGE_TYPE.GAME_JOINED),
    }),
    z.transform((raw) => ({
        pendingGameSeconds: raw[WIRE_KEY.PENDING_GAME_TIMEOUT],
        type: "game_joined" as const,
    })),
);

/**
 * A seat changing hands, live as a replay's seat control line records it, so it parses into the same shapes: an AI
 * player stands in for the seat's human (`WIRE_KEY.SEAT_CONTROL_REASON` says why), or without `WIRE_KEY.SEAT_CONTROL_REASON`, the human takes it back.
 */
const seatControlSchema = z.pipe(
    z.object({
        [WIRE_KEY.SEAT_CONTROL_REASON]: z.optional(seatControlReasonSchema),
        [WIRE_KEY.SEAT]: seatSchema,
        [WIRE_KEY.SESSION_TYPE]: z.literal(SESSION_MESSAGE_TYPE.SEAT_CONTROL),
    }),
    z.transform((raw) => {
        const reason = raw[WIRE_KEY.SEAT_CONTROL_REASON];
        return reason === undefined
            ? { seat: raw[WIRE_KEY.SEAT], type: "human_return" as const }
            : { reason, seat: raw[WIRE_KEY.SEAT], type: "ai_replacement" as const };
    }),
);

// --- Dispatch ---

export type SessionErrorMessage = z.output<typeof sessionErrorSchema>;
export type GameJoinedMessage = z.output<typeof gameJoinedSchema>;
export type SeatControlMessage = z.output<typeof seatControlSchema>;

export type SessionMessage = SessionErrorMessage | GameJoinedMessage | SeatControlMessage;

export function parseSessionMessage(raw: Record<string, unknown>): SessionMessage {
    const { [WIRE_KEY.SESSION_TYPE]: type } = raw;
    switch (type) {
        case SESSION_MESSAGE_TYPE.ERROR: {
            return sessionErrorSchema.parse(raw);
        }
        case SESSION_MESSAGE_TYPE.GAME_JOINED: {
            return gameJoinedSchema.parse(raw);
        }
        case SESSION_MESSAGE_TYPE.SEAT_CONTROL: {
            return seatControlSchema.parse(raw);
        }
        default: {
            throw new Error(`Unknown session message type: SESSION_TYPE=${String(type)}`);
        }
    }
}
