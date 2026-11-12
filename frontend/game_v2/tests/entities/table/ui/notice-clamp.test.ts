import { describe, expect, it } from "vitest";

import {
    type NoticeMeasure,
    type ToastMeasure,
    planNoticeClamp,
    planToastStack,
} from "@/entities/table/ui/notice-clamp";

const LINE = 14;
const GAP = 6;

/** A clampable notice of `lines` lines of text, with 8px of padding and rim, and `wholeExtra` more shown whole. */
function notice(lines: number, clampable = true, wholeExtra = 0): NoticeMeasure {
    return { chrome: 8, clampable, lineHeight: LINE, textHeight: lines * LINE, wholeExtra };
}

describe("planNoticeClamp", () => {
    it("shows a stack that fits its place whole", () => {
        expect(planNoticeClamp(200, GAP, [notice(3), notice(2)])).toEqual({
            lines: [null, null],
            shown: 2,
        });
    });

    it("clamps the tallest notice to the most whole lines that let the stack fit, its Show all a line of its own", () => {
        const plan = planNoticeClamp(120, GAP, [notice(2), notice(9)]);

        expect(plan).toEqual({ lines: [null, 4], shown: 2 });
    });

    it("keeps a clamped notice at least a tap target high, one line at the least", () => {
        expect(planNoticeClamp(42, GAP, [notice(6)])).toEqual({ lines: [1], shown: 1 });
    });

    it("leaves out the last notices a short place cannot hold even clamped, the last shown clamped to open them", () => {
        const plan = planNoticeClamp(45, GAP, [notice(5), notice(1)]);

        expect(plan).toEqual({ lines: [1, null], shown: 1 });
    });

    it("counts the room a notice's way out takes shown whole, never once it is clamped", () => {
        expect(planNoticeClamp(60, GAP, [notice(1), notice(1, true, 18)])).toEqual({
            lines: [1, null],
            shown: 1,
        });
        expect(planNoticeClamp(42, GAP, [notice(2, true, 18)])).toEqual({ lines: [1], shown: 1 });
    });

    it("never clamps a notice to all its lines, which would hide only its way out", () => {
        expect(planNoticeClamp(52, GAP, [notice(2, true, 18)])).toEqual({ lines: [1], shown: 1 });
        expect(planNoticeClamp(45, GAP, [notice(1, true, 30)])).toEqual({
            lines: [null],
            shown: 1,
        });
    });

    it("never clamps a notice the board cannot open whole", () => {
        expect(planNoticeClamp(60, GAP, [notice(6, false)])).toEqual({ lines: [null], shown: 1 });
    });
});

function toast(lines: number, cutPastTwoLines = false, clampable = true): ToastMeasure {
    const wholeHeight = 8 + Math.min(lines, 2) * LINE;
    return { clampable, clampedHeight: Math.max(40, wholeHeight), cutPastTwoLines, wholeHeight };
}

describe("planToastStack", () => {
    it("shows two-line toasts whole, clamping only one whose words run past its two lines", () => {
        expect(planToastStack(200, GAP, [toast(2), toast(1), toast(3, true)])).toEqual({
            clamped: [false, false, true],
            shown: 3,
        });
    });

    it("leaves out the last toasts the place cannot hold, the last shown clamped a tap target high to open them", () => {
        expect(planToastStack(80, GAP, [toast(1), toast(2), toast(2)])).toEqual({
            clamped: [false, true, false],
            shown: 2,
        });
        expect(planToastStack(60, GAP, [toast(2), toast(2)])).toEqual({
            clamped: [true, false],
            shown: 1,
        });
    });
});
