import { describe, expect, it } from "vitest";

import { SIDEWAYS_UNITS, STACKED_DEPTH, UPRIGHT_DEPTH } from "@/entities/table/lib/board-constants";
import { type StripContent, type StripRooms, stripLayout } from "@/entities/table/lib/strip-layout";

const CHI = { depth: UPRIGHT_DEPTH, units: 2 + SIDEWAYS_UNITS };
const ADDED_KAN = { depth: STACKED_DEPTH, units: 2 + SIDEWAYS_UNITS };
const FOUR_CHI: StripContent = { drawn: true, hand: 2, melds: [CHI, CHI, CHI, CHI] };
const SIDE = { deepLine: 300, line: 300, secondAt: 0, secondLine: 200 };
const ROOMS: StripRooms = {
    gap: 8,
    left: SIDE,
    right: SIDE,
    rw: 20,
    top: { anchor: 300, badgeDepth: 100, cap: null, depth: 100, lane: 0, start: 0 },
};

describe("stripLayout", () => {
    it("puts a side strip's oldest meld that misses its line on a second line, where the top strip scales", () => {
        const side = stripLayout("right", FOUR_CHI, ROOMS).melds;
        const top = stripLayout("top", FOUR_CHI, ROOMS).melds;

        expect(side.map((meld) => meld.rise > 0)).toEqual([false, false, false, true]);
        expect(side.slice(0, 3).every((meld) => meld.tile === ROOMS.rw)).toBe(true);
        expect(top.every((meld) => meld.rise === 0 && meld.tile < ROOMS.rw)).toBe(true);
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
            const [chi, kan] = stripLayout("left", content, { ...ROOMS, left }).melds;
            const last = wraps ? chi : kan;

            expect(kan?.rise !== 0).toBe(wraps);
            expect(chi?.rise).toBe(0);
            expect((last?.along ?? 0) + CHI.units * ROOMS.rw).toBeCloseTo(end, 6);
        },
    );
});
