import { describe, expect, it } from "vitest";

import { SIDEWAYS_UNITS, UPRIGHT_DEPTH } from "@/entities/table/lib/board-constants";
import { type StripContent, type StripRooms, stripLayout } from "@/entities/table/lib/strip-layout";

const CHI = { depth: UPRIGHT_DEPTH, units: 2 + SIDEWAYS_UNITS };
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
});
