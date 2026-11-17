import { describe, expect, it } from "vitest";

import { DEFAULT_REPLAY_PREFS, readReplayPrefs } from "@/entities/replay";

describe("readReplayPrefs", () => {
    it("keeps only the readable fields of what was stored, the defaults for the rest", () => {
        expect([
            readReplayPrefs({ hideHands: true, speed: 2 }),
            readReplayPrefs({ hideHands: "yes", showTsumogiri: false }),
            readReplayPrefs("not settings"),
        ]).toEqual([
            { hideHands: true, showTsumogiri: true },
            { hideHands: false, showTsumogiri: false },
            DEFAULT_REPLAY_PREFS,
        ]);
    });
});
