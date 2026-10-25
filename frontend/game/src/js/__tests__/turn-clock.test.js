import { describe, expect, it } from "vitest";

import TurnClock from "../ronin/clock.js";

describe("TurnClock", () => {
    it("caps the bank the round bonuses add up to, and drains it to zero at most", () => {
        let now = 0;
        const clock = new TurnClock(() => now);
        clock.configure({ tb: 5, bk: 50, rb: 10, mb: 60, md: 5 });

        clock.addRoundBonus();
        clock.addRoundBonus();
        expect(clock.startTurn()).toEqual([5, 60]);

        now += 90_000;
        clock.stop();
        expect(clock.startTurn()).toEqual([5, 0]);
    });
});
