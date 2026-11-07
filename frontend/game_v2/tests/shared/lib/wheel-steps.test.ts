import { describe, expect, it } from "vitest";

import { type WheelGesture, holdWheel, wheelStep } from "@/shared/lib";

/** Feed `[deltaPx, atMs]` wheel events into one gesture, from `start`, and return the step each took. */
function steps(
    events: readonly (readonly [number, number])[],
    start: WheelGesture | null = null,
): number[] {
    let gesture = start;
    return events.map(([delta, at]) => {
        const { gesture: after, step } = wheelStep(gesture, delta, at);
        gesture = after;
        return step;
    });
}

describe("wheelStep", () => {
    it("steps once a trackpad's ticks add up, then only every further stretch and beat", () => {
        expect(
            steps([
                [10, 0],
                [10, 20],
                [10, 40],
                [40, 50],
                [20, 60],
                [10, 80],
            ]),
        ).toEqual([0, 0, 1, 0, 0, 1]);
    });

    it("steps at once on a mouse notch, and starts over when the wheel turns back", () => {
        expect(
            steps([
                [100, 0],
                [-20, 50],
                [-20, 60],
            ]),
        ).toEqual([1, 0, -1]);
    });

    it("counts no distance while held, so a momentum tail after the hold steps only once it runs a stretch again", () => {
        const first = wheelStep(null, 100, 0);
        const afterHold = steps(
            [
                [100, 150],
                [100, 300],
                [100, 450],
                [1, 500],
                [1, 530],
                [1, 560],
                [50, 590],
            ],
            holdWheel(first.gesture, 500),
        );

        expect([first.step, ...afterHold]).toEqual([1, 0, 0, 0, 0, 0, 0, 1]);
    });

    it("steps back at once when the wheel turns back during a hold", () => {
        const held = holdWheel(wheelStep(null, 100, 0).gesture, 500);

        expect(wheelStep(held, -100, 100).step).toBe(-1);
    });
});
