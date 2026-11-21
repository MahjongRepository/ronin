import { decode } from "@msgpack/msgpack";
import { z } from "zod/mini";

import { NUM_PLAYERS } from "@/shared/protocol/constants";

const observeAnswerSchema = z.pipe(
    z.object({
        available_in_ms: z.int().check(z.minimum(0)),
        ended: z.boolean(),
        game_type: z.string(),
        next: z.int().check(z.minimum(0)),
        players: z.array(z.string()).check(z.length(NUM_PLAYERS)),
        records: z.custom<Uint8Array>((value) => value instanceof Uint8Array),
        started_at: z.int(),
    }),
    z.transform((raw) => ({
        availableInMs: raw.available_in_ms,
        ended: raw.ended,
        gameType: raw.game_type,
        next: raw.next,
        players: raw.players,
        records: raw.records,
        startedAt: raw.started_at,
    })),
);

/**
 * One answer of a game's observe stream (`docs/architecture.md`, Game client contract): the game's start, type and
 * players East to North, the time left before its first records may be watched, the cursor after the records it
 * carries, whether the stream has ended, and those records as replay bytes.
 */
export type ObserveAnswer = z.output<typeof observeAnswerSchema>;

/** Decode an observe answer's body; throws on bytes that are not one such map. */
export function decodeObserveAnswer(body: Uint8Array): ObserveAnswer {
    return observeAnswerSchema.parse(decode(body));
}
