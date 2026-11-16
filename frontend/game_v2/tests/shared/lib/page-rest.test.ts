import { describe, expect, test } from "vitest";

import { ManualClock } from "#tests/fixtures/clock";
import { keepPageRested } from "@/shared/lib";

const QUIET_MS = 150;
const REST = 100;

class FakePage extends EventTarget {
    scrollY = 0;

    scrollTo = (_left: number, top: number): void => {
        this.scrollY = top;
    };

    /** The reader scrolls the page to `y`, by a drag or its fling. */
    scrollBy(top: number): void {
        this.scrollY = top;
        this.dispatchEvent(new Event("scroll"));
    }

    touch(type: "touchstart" | "touchend", fingersDown: number): void {
        const touches = Array.from({ length: fingersDown }, () => ({}));
        this.dispatchEvent(Object.assign(new Event(type), { touches }));
    }
}

function restedPage(restAt = REST): { clock: ManualClock; page: FakePage; stop: () => void } {
    const clock = new ManualClock();
    const page = new FakePage();
    const { stop } = keepPageRested(page, { clock, quietMs: QUIET_MS, restAt: () => restAt });
    return { clock, page, stop };
}

describe("keepPageRested", () => {
    test("returns the page to its rest once a run of scrolls above it settles", () => {
        const { clock, page } = restedPage();

        page.scrollBy(0);
        clock.advanceTo(100);
        page.scrollBy(40);
        clock.advanceTo(249);
        expect(page.scrollY).toBe(40);

        clock.advanceTo(250);
        expect(page.scrollY).toBe(REST);
    });

    test("returns the page to its rest from below it, where a swipe up leaves it", () => {
        const { clock, page } = restedPage();

        page.scrollBy(380);
        clock.advanceTo(QUIET_MS);

        expect(page.scrollY).toBe(REST);
    });

    test("leaves the page where a finger holds it, and rests it once the finger lifts", () => {
        const { clock, page } = restedPage();

        page.touch("touchstart", 1);
        page.scrollBy(240);
        clock.advanceTo(1000);
        expect(page.scrollY).toBe(240);

        page.touch("touchend", 0);
        clock.advanceTo(1150);
        expect(page.scrollY).toBe(REST);
    });

    test("leaves a page that keeps no scroll room where it is", () => {
        const { clock, page } = restedPage(0);

        page.scrollBy(40);
        clock.advanceTo(1000);

        expect(page.scrollY).toBe(40);
    });

    test("stopping drops a rest still waiting", () => {
        const { clock, page, stop } = restedPage();

        page.scrollBy(40);
        stop();
        clock.advanceTo(1000);

        expect(page.scrollY).toBe(40);
    });
});
