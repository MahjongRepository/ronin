import { describe, expect, it } from "vitest";

import { DEFAULT_REPLAY_PREFS, readReplayPrefs } from "@/entities/table";

describe("readReplayPrefs", () => {
    it("keeps only the readable fields of what was stored, the defaults for the rest", () => {
        expect([
            readReplayPrefs({ hideHands: true, speed: 2 }),
            readReplayPrefs({ hideHands: "yes", speed: 4 }),
            readReplayPrefs("not settings"),
        ]).toEqual([
            { hideHands: true, speed: 2 },
            { hideHands: false, speed: 4 },
            DEFAULT_REPLAY_PREFS,
        ]);
    });
});
