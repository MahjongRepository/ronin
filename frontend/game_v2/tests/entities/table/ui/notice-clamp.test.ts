import { describe, expect, it } from "vitest";

import { type NoticeMeasure, planNoticeClamp } from "@/entities/table/ui/notice-clamp";

const LINE = 14;
const GAP = 6;

/** A clampable notice of `lines` lines of text, with 8px of padding and rim. */
function notice(lines: number, clampable = true): NoticeMeasure {
    return { chrome: 8, clampable, lineHeight: LINE, textHeight: lines * LINE };
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

    it("never clamps a notice the board cannot open whole", () => {
        expect(planNoticeClamp(60, GAP, [notice(6, false)])).toEqual({ lines: [null], shown: 1 });
    });
});
