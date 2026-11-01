import { describe, expect, test, vi } from "vitest";

import { REPLAY_GAME_STARTED, REPLAY_ROUND_STARTED } from "#tests/fixtures/wire";
import { readReplayTimeline } from "@/entities/client";
import { REPLAY_VERSION } from "@/shared/protocol";

vi.mock(import("@/entities/table"), async (importOriginal) => {
    const table = await importOriginal();
    return {
        ...table,
        applyEvent: (state, event) => {
            if (event.type === "discard") {
                throw new TypeError("a bug in the discard handler");
            }
            return table.applyEvent(state, event);
        },
    };
});

describe("readReplayTimeline - a bug in the client", () => {
    test("throws a table error that is no DesyncError rather than calling the recording damaged", () => {
        const text = [
            JSON.stringify({ version: REPLAY_VERSION }),
            JSON.stringify(REPLAY_GAME_STARTED),
            JSON.stringify(REPLAY_ROUND_STARTED),
            '{"d": 0, "t": 1, "tr": 69}',
            '{"d": 0, "t": 2}',
        ].join("\n");

        expect(() => readReplayTimeline(text)).toThrow("a bug in the discard handler");
    });
});
