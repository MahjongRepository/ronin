import { describe, expect, it } from "vitest";

import {
    FACE_FLOOR,
    SIDEWAYS_UNITS,
    STACKED_DEPTH,
    UPRIGHT_DEPTH,
} from "@/entities/table/lib/board-constants";
import { type BoardBox, boardGeometry } from "@/entities/table/lib/board-geometry";
import {
    type StripContent,
    type StripRooms,
    handLength,
    stripLayout,
} from "@/entities/table/lib/strip-layout";

const CHI = { depth: UPRIGHT_DEPTH, units: 2 + SIDEWAYS_UNITS };
const ADDED_KAN = { depth: STACKED_DEPTH, units: 2 + SIDEWAYS_UNITS };
const OPEN_KAN = { depth: UPRIGHT_DEPTH, units: 3 + SIDEWAYS_UNITS };
const CLOSED_KAN = { depth: UPRIGHT_DEPTH, units: 4 };
const SIDE = { deepLine: 300, line: 300, obstacles: [] };
const ROOMS: StripRooms = {
    gap: 8,
    left: SIDE,
    right: SIDE,
    rw: 20,
    top: { anchor: 300, badgeDepth: 100, cap: null, depth: 100, lane: 0, start: 0 },
};

function windowStrips(box: BoardBox): StripRooms {
    const { strips } = boardGeometry({
        box,
        gutter: 0,
        safeInsets: { bottom: 0, left: 0, right: 0, top: 0 },
        slots: { band: "play" },
    });
    if (!strips) {
        throw new Error("The board has no strip rooms");
    }
    return strips;
}

describe("stripLayout", () => {
    it.each(["left", "right"] as const)(
        "keeps every %s meld in one ordered line beside the hand, scaling all shapes together",
        (seat) => {
            const content: StripContent = {
                drawn: true,
                hand: 2,
                melds: [ADDED_KAN, OPEN_KAN, CLOSED_KAN, CHI],
            };
            const { melds } = stripLayout(seat, content, ROOMS);
            expect(melds.map((meld) => meld.rise)).toEqual([0, 0, 0, 0]);
            expect(melds.map((meld) => meld.tile)).toEqual([14, 14, 14, 14]);
            expect(melds[0]?.along).toBeGreaterThanOrEqual(
                handLength(content.hand, true, ROOMS.rw) + ROOMS.gap,
            );
            for (const [index, shape] of content.melds.entries()) {
                const meld = melds[index];
                const end = (meld?.along ?? Number.NaN) + shape.units * (meld?.tile ?? Number.NaN);
                expect(end).toBeCloseTo(
                    index === melds.length - 1
                        ? SIDE.line
                        : (melds[index + 1]?.along ?? Number.NaN) - ROOMS.gap,
                    6,
                );
            }
        },
    );

    it.each([
        { height: 375, width: 667 },
        { height: 491, width: 704 },
        { height: 540, width: 700 },
        { height: 800, width: 1280 },
    ])("fits four open kans on one line at $width x $height", (box) => {
        const strips = windowStrips(box);
        const content: StripContent = {
            drawn: true,
            hand: 2,
            melds: [OPEN_KAN, OPEN_KAN, OPEN_KAN, OPEN_KAN],
        };
        for (const seat of ["left", "right"] as const) {
            const { melds } = stripLayout(seat, content, strips);
            expect(melds.map((meld) => meld.rise)).toEqual([0, 0, 0, 0]);
            expect(melds[0]?.along).toBeGreaterThanOrEqual(
                handLength(content.hand, true, strips.rw) + strips.gap - 0.001,
            );
            expect(melds.every((meld) => meld.tile >= FACE_FLOOR)).toBe(true);
            const [, , , oldest] = melds;
            expect(
                (oldest?.along ?? Number.NaN) + OPEN_KAN.units * (oldest?.tile ?? Number.NaN),
            ).toBeLessThanOrEqual(strips[seat].line + 0.001);
        }
    });

    it("fits a lone added kan past the switches once scaling makes its stack shallow enough", () => {
        const left = {
            deepLine: 245,
            line: 400,
            obstacles: [{ depth: 30, from: 245, to: 400 }],
        };
        const content: StripContent = { drawn: true, hand: 11, melds: [ADDED_KAN] };
        const { melds } = stripLayout("left", content, { ...ROOMS, left });
        expect(melds).toHaveLength(1);
        const [kan] = melds;
        expect(kan?.rise).toBe(0);
        expect(kan?.tile).toBe(14);
        expect(kan?.along).toBeGreaterThan(handLength(content.hand, true, ROOMS.rw));
        expect((kan?.along ?? Number.NaN) + ADDED_KAN.units * (kan?.tile ?? 0)).toBeCloseTo(
            left.line,
            6,
        );
    });

    it("keeps the top strip at the river tile where its stacked kan stands past the badge's lane", () => {
        const top = { ...ROOMS.top, badgeDepth: 30, lane: 200 };
        const content: StripContent = { drawn: true, hand: 2, melds: [CHI, ADDED_KAN] };
        const { melds } = stripLayout("top", content, { ...ROOMS, top });
        expect(melds.map((meld) => meld.tile)).toEqual([ROOMS.rw, ROOMS.rw]);
        expect(melds[0]?.along).toBeLessThan(top.lane);
        expect(melds[1]?.along).toBeGreaterThan(top.lane);
    });
});
