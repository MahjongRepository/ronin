import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_REPLAY_PREFS, localReplayPrefs } from "@/entities/table";

afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
});

describe("localReplayPrefs", () => {
    it("reads back what it saved, and keeps only the readable fields of anything else stored", () => {
        localReplayPrefs.save({ hideHands: true, speed: 2 });
        const saved = localReplayPrefs.load();
        localStorage.setItem("ronin.v2.replay-prefs", '{"hideHands": "yes", "speed": 4}');
        const partial = localReplayPrefs.load();
        localStorage.setItem("ronin.v2.replay-prefs", "{broken");

        expect([saved, partial]).toEqual([
            { hideHands: true, speed: 2 },
            { hideHands: false, speed: 4 },
        ]);
        expect(localReplayPrefs.load()).toEqual(DEFAULT_REPLAY_PREFS);
    });

    it("gives the defaults and keeps nothing where storage is blocked", () => {
        vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
            throw new DOMException("blocked", "SecurityError");
        });

        expect(() => localReplayPrefs.save({ hideHands: true, speed: 2 })).not.toThrow();
        expect(localReplayPrefs.load()).toEqual(DEFAULT_REPLAY_PREFS);
    });
});
