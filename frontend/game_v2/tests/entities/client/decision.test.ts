import { assert, describe, expect, it } from "vitest";

import { checkpointState, loadSeatScenario } from "#tests/fixtures/seat-transcripts";
import { wireRuleRefusal, wireSessionError } from "#tests/fixtures/wire";
import { followDecision } from "@/entities/client/model/decision";
import { SEAT_TRANSCRIPTS } from "@/fixtures/seat-transcripts";
import {
    type ParsedServerMessage,
    SESSION_ERROR_CODE,
    parseServerMessage,
} from "@/shared/protocol";

/** The first message of each type any generated transcript's seat received, with the refusals no transcript holds. */
function messageOfEachType(waitId: number): ReadonlyMap<string, ParsedServerMessage> {
    const payloads = [
        ...[...SEAT_TRANSCRIPTS.keys()].flatMap((name) =>
            loadSeatScenario(name).transcript.events.flatMap((event) =>
                event.kind === "received" ? [event.payload] : [],
            ),
        ),
        wireRuleRefusal(waitId),
        wireSessionError(SESSION_ERROR_CODE.RATE_LIMITED, waitId),
    ];
    const byType = new Map<string, ParsedServerMessage>();
    for (const payload of payloads) {
        const [error, message] = parseServerMessage(payload);
        if (error) {
            throw error;
        }
        if (!byType.has(message.type)) {
            byType.set(message.type, message);
        }
    }
    return byType;
}

describe("followDecision", () => {
    it("closes an open decision on a message of the server moving on, and keeps it through any other", () => {
        const { decision } = checkpointState("call_prompt_seat_1", "prompt");
        assert(decision?.status.kind === "open");
        const followed = [...messageOfEachType(decision.waitId)].map(
            ([type, message]) => [type, followDecision(decision, message)] as const,
        );
        function typesFollowedBy(outcome: typeof decision | null): string[] {
            return followed.filter(([, next]) => next === outcome).map(([type]) => type);
        }
        const closing = typesFollowedBy(null);
        const keeping = typesFollowedBy(decision);

        expect(closing.length + keeping.length).toBe(followed.length);
        expect(closing.toSorted()).toEqual([
            "call_prompt",
            "discard",
            "draw",
            "draw_notice",
            "game_end",
            "game_reconnected",
            "game_started",
            "meld",
            "round_end",
            "round_started",
            "turn",
        ]);
        expect(keeping.toSorted()).toEqual([
            "ai_replacement",
            "dora_revealed",
            "error",
            "furiten",
            "human_return",
            "riichi_declared",
            "session_error",
        ]);
    });
});
