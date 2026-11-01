import { describe, expect, it } from "vitest";

import { ManualClock, steadyClockOn } from "#tests/fixtures/clock";

const HOUR_MS = 3_600_000;

describe("createSteadyClock", () => {
    it("runs on at the elapsed rate after the wall clock steps back, never running back itself", () => {
        const manual = new ManualClock();
        const clock = steadyClockOn(manual);
        manual.advanceTo(5000);
        const before = clock.now();

        manual.stepWall(-HOUR_MS);
        manual.advanceTo(5500);
        const after = clock.now();
        manual.advanceTo(6000);

        expect([before, after, clock.now()]).toEqual([5000, 5500, 6000]);
    });

    it("counts a sleep as time that passed, whether elapsed time ran through it or paused", () => {
        const ranThrough = new ManualClock();
        const ranClock = steadyClockOn(ranThrough);
        const paused = new ManualClock();
        const pausedClock = steadyClockOn(paused);

        ranThrough.advanceTo(HOUR_MS);
        paused.stepWall(HOUR_MS);

        expect([ranClock.now(), pausedClock.now()]).toEqual([HOUR_MS, HOUR_MS]);
    });

    it("takes a forward step that sets the wall right after a back step as no time passing", () => {
        const manual = new ManualClock();
        const clock = steadyClockOn(manual);
        manual.stepWall(-HOUR_MS);
        manual.advanceTo(1000);
        const stepped = clock.now();

        manual.stepWall(HOUR_MS);
        manual.advanceTo(2000);

        expect([stepped, clock.now()]).toEqual([1000, 2000]);
    });

    it("counts a sleep long after a back step that was never undone as time that passed", () => {
        const manual = new ManualClock();
        const clock = steadyClockOn(manual);
        manual.stepWall(-20 * 60_000);
        const stepped = clock.now();
        manual.advanceTo(15 * 60_000);
        const beforeSleep = clock.now();

        manual.stepWall(15 * 60_000);

        expect([stepped, beforeSleep, clock.now()]).toEqual([0, 15 * 60_000, 30 * 60_000]);
    });

    it("follows the wall within its tolerance, holding still while it falls behind", () => {
        const manual = new ManualClock();
        const clock = steadyClockOn(manual);
        manual.advanceTo(1000);
        const before = clock.now();
        manual.stepWall(-400);
        const held = clock.now();

        manual.advanceTo(2000);

        expect([before, held, clock.now()]).toEqual([1000, 1000, 1600]);
    });
});
