import { describe, expect, test } from "vitest";

import { ManualClock } from "#tests/fixtures/clock";
import { onScrollSettled } from "@/shared/lib";

const QUIET_MS = 150;

function settledOn(clock: ManualClock): {
    scroll: () => void;
    settled: () => number;
    stop: () => void;
} {
    const target = new EventTarget();
    let count = 0;
    const stop = onScrollSettled(target, {
        clock,
        listener: () => {
            count += 1;
        },
        quietMs: QUIET_MS,
    });
    return {
        scroll: () => target.dispatchEvent(new Event("scroll")),
        settled: () => count,
        stop,
    };
}

describe("onScrollSettled", () => {
    test("waits out a run of scrolls, counting from the last one", () => {
        const clock = new ManualClock();
        const { scroll, settled } = settledOn(clock);

        scroll();
        clock.advanceTo(100);
        scroll();
        clock.advanceTo(249);
        expect(settled()).toBe(0);

        clock.advanceTo(250);
        expect(settled()).toBe(1);
    });

    test("calls again for a later scroll", () => {
        const clock = new ManualClock();
        const { scroll, settled } = settledOn(clock);
        scroll();
        clock.advanceTo(150);

        scroll();
        clock.advanceTo(300);

        expect(settled()).toBe(2);
    });

    test("stopping drops a settle still waiting and any later scroll", () => {
        const clock = new ManualClock();
        const { scroll, settled, stop } = settledOn(clock);

        scroll();
        stop();
        scroll();
        clock.advanceTo(1000);

        expect(settled()).toBe(0);
    });
});
