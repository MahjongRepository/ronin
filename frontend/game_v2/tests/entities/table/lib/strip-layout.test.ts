import { describe, expect, it } from "vitest";

import {
    SIDEWAYS_UNITS,
    STACKED_DEPTH,
    STRIP_LINES_GAP,
    UPRIGHT_DEPTH,
} from "@/entities/table/lib/board-constants";
import { type StripContent, type StripRooms, stripLayout } from "@/entities/table/lib/strip-layout";

const CHI = { depth: UPRIGHT_DEPTH, units: 2 + SIDEWAYS_UNITS };
const ADDED_KAN = { depth: STACKED_DEPTH, units: 2 + SIDEWAYS_UNITS };
const FOUR_CHI: StripContent = { drawn: true, hand: 2, melds: [CHI, CHI, CHI, CHI] };
const SIDE = { deepLine: 300, line: 300, secondAt: 250, secondLine: 200 };
const ROOMS: StripRooms = {
    gap: 8,
    left: SIDE,
    right: SIDE,
    rw: 20,
    top: { anchor: 300, badgeDepth: 100, cap: null, depth: 100, lane: 0, start: 0 },
};

describe("stripLayout", () => {
    it.each(["left", "right"] as const)(
        "keeps the %s strip's overflow at the meld end, where the top strip scales",
        (seat) => {
            const side = stripLayout(seat, FOUR_CHI, ROOMS).melds;
            const top = stripLayout("top", FOUR_CHI, ROOMS).melds;

            expect(side.map((meld) => meld.rise > 0)).toEqual([false, false, false, true]);
            expect(side.slice(0, 3).every((meld) => meld.tile === ROOMS.rw)).toBe(true);
            const [, , , overflow] = side;
            expect(overflow).toBeDefined();
            expect((overflow?.along ?? Number.NaN) + CHI.units * (overflow?.tile ?? 0)).toBeCloseTo(
                SIDE.secondAt,
                6,
            );
            expect(top.every((meld) => meld.rise === 0 && meld.tile < ROOMS.rw)).toBe(true);
        },
    );

    it("keeps a wrapped added kan beside the first row without reserving its stack in both rows", () => {
        const content: StripContent = { drawn: true, hand: 5, melds: [CHI, CHI, ADDED_KAN] };
        const right = { ...SIDE, secondLine: 50 };
        const { melds, depth } = stripLayout("right", content, { ...ROOMS, right });
        expect(melds.map((meld) => meld.rise > 0)).toEqual([false, false, true]);
        expect(melds[2]?.rise).toBeCloseTo(UPRIGHT_DEPTH * ROOMS.rw + STRIP_LINES_GAP, 6);
        expect(melds[2]?.tile).toBeCloseTo(15, 6);
        expect(depth).toBeCloseTo((melds[2]?.rise ?? Number.NaN) + STACKED_DEPTH * 15, 6);
    });

    it("keeps the top strip at the river tile where its stacked kan stands past the badge's lane", () => {
        const top = { ...ROOMS.top, badgeDepth: 30, lane: 200 };
        const content: StripContent = { drawn: true, hand: 2, melds: [CHI, ADDED_KAN] };
        const { melds } = stripLayout("top", content, { ...ROOMS, top });

        expect(melds.map((meld) => meld.tile)).toEqual([ROOMS.rw, ROOMS.rw]);
        expect(melds[0]?.along).toBeLessThan(top.lane);
        expect(melds[1]?.along).toBeGreaterThan(top.lane);
    });

    it.each([
        { deepLine: 200, end: 200, wraps: false },
        { deepLine: 150, end: 400, wraps: true },
    ])(
        "holds a left strip's chi and added kan to the kan's stacked room ($deepLine), wrapping it past ($wraps)",
        ({ deepLine, end, wraps }) => {
            const left = { ...SIDE, deepLine, line: 400 };
            const content: StripContent = { drawn: true, hand: 2, melds: [CHI, ADDED_KAN] };
            const { melds } = stripLayout("left", content, { ...ROOMS, left });
            const last = melds[wraps ? 0 : 1];

            expect(melds.map((meld) => meld.rise > 0)).toEqual([false, wraps]);
            expect((last?.along ?? 0) + CHI.units * ROOMS.rw).toBeCloseTo(end, 6);
        },
    );
});
