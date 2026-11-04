import { describe, expect, test, vi } from "vitest";

import { encodeReplayLines } from "#tests/fixtures/replay-records";
import { REPLAY_GAME_STARTED, REPLAY_ROUND_STARTED } from "#tests/fixtures/wire";
import { readReplayTimeline } from "@/entities/client";
import { REPLAY_VERSION, WIRE_KEY } from "@/shared/protocol";

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
            JSON.stringify({ [WIRE_KEY.REPLAY_VERSION]: REPLAY_VERSION }),
            JSON.stringify(REPLAY_GAME_STARTED),
            JSON.stringify(REPLAY_ROUND_STARTED),
            JSON.stringify({
                [WIRE_KEY.PACKED_MOVE]: 0,
                [WIRE_KEY.EVENT_TYPE]: 1,
                [WIRE_KEY.TILES_REMAINING]: 69,
            }),
            JSON.stringify({ [WIRE_KEY.PACKED_MOVE]: 0, [WIRE_KEY.EVENT_TYPE]: 2 }),
        ].join("\n");

        expect(() => readReplayTimeline(encodeReplayLines(text))).toThrow(
            "a bug in the discard handler",
        );
    });
});
