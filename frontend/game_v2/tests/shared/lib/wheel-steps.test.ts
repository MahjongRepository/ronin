import { describe, expect, it } from "vitest";

import { type WheelGesture, wheelStep } from "@/shared/lib";

/** Feed `[deltaPx, atMs]` wheel events into one gesture and return the step each took. */
function steps(events: readonly (readonly [number, number])[]): number[] {
    let gesture: WheelGesture | null = null;
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
});
