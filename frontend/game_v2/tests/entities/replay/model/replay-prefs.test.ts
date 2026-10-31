import { describe, expect, it } from "vitest";

import { DEFAULT_REPLAY_PREFS, readReplayPrefs } from "@/entities/replay";

describe("readReplayPrefs", () => {
    it("keeps only the readable fields of what was stored, the defaults for the rest", () => {
        expect([
            readReplayPrefs({ hideHands: true, speed: 2 }),
            readReplayPrefs({ hideHands: "yes" }),
            readReplayPrefs("not settings"),
        ]).toEqual([{ hideHands: true }, { hideHands: false }, DEFAULT_REPLAY_PREFS]);
    });
});
