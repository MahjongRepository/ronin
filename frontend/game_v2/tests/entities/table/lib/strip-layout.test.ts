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
    ownMeldLayout,
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
    it("lays a short phone's two added kans at the face floor past the switches and the badge where their line cannot hold them", () => {
        const rooms = windowStrips({ height: 236, width: 667 });
        const content: StripContent = { drawn: true, hand: 8, melds: [ADDED_KAN, ADDED_KAN] };

        const { melds } = stripLayout("left", content, rooms);

        expect(rooms.rw).toBeLessThan(FACE_FLOOR);
        expect(melds.map((meld) => meld.tile)).toEqual([FACE_FLOOR, FACE_FLOOR]);
        expect(melds[0]?.along).toBeGreaterThanOrEqual(
            handLength({ drawn: true, rw: rooms.rw, seat: "left", tiles: 8 }) + rooms.gap,
        );
        for (const [index, meld] of melds.entries()) {
            const [depth, end] = [
                ADDED_KAN.depth * meld.tile,
                meld.along + ADDED_KAN.units * meld.tile,
            ];
            for (const obstacle of rooms.left.obstacles) {
                expect(
                    depth > obstacle.depth && meld.along < obstacle.to && end > obstacle.from,
                    `meld ${String(index)} (${String(depth)}px deep at ${String(meld.along)}..${String(end)}) over the obstacle ${String(obstacle.from)}..${String(obstacle.to)} at depth ${String(obstacle.depth)}`,
                ).toBe(false);
            }
        }
    });

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
                handLength({ drawn: true, rw: ROOMS.rw, seat, tiles: content.hand }) + ROOMS.gap,
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
                handLength({ drawn: true, rw: strips.rw, seat, tiles: content.hand }) +
                    strips.gap -
                    0.001,
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
        expect(kan?.along).toBeGreaterThan(
            handLength({ drawn: true, rw: ROOMS.rw, seat: "left", tiles: content.hand }),
        );
        expect((kan?.along ?? Number.NaN) + ADDED_KAN.units * (kan?.tile ?? 0)).toBeCloseTo(
            left.line,
            6,
        );
    });

    it("keeps the top strip at the river tile where its stacked kan stands past the badge's lane", () => {
        const top = { ...ROOMS.top, anchor: 400, badgeDepth: 30, lane: 300 };
        const content: StripContent = { drawn: true, hand: 8, melds: [CHI, ADDED_KAN] };
        const { melds } = stripLayout("top", content, { ...ROOMS, top });
        expect(melds.map((meld) => meld.tile)).toEqual([ROOMS.rw, ROOMS.rw]);
        expect(melds[0]?.along).toBeLessThan(top.lane);
        expect(melds[1]?.along).toBeGreaterThan(top.lane);
    });

    it("lays every opponent's strip out alike whether its hand has just discarded, drawn or called", () => {
        const boxes = [
            { height: 375, width: 667 },
            { height: 390, width: 844 },
            { height: 748, width: 1004 },
            { height: 700, width: 1260 },
            { height: 748, width: 1346 },
            { height: 1380, width: 1484 },
            { height: 1060, width: 1900 },
            { height: 1004, width: 748 },
            { height: 844, width: 390 },
        ];
        const sets = [
            [CHI],
            [CHI, CHI],
            [OPEN_KAN, CHI, ADDED_KAN],
            [CHI, CHI, CHI, CHI],
            [CLOSED_KAN, CLOSED_KAN, CLOSED_KAN, CLOSED_KAN],
        ];
        const unsteady = boxes.flatMap((box) => {
            const rooms = windowStrips(box);
            return (["left", "top", "right"] as const).flatMap((seat) =>
                sets.flatMap((melds) => {
                    const full = 14 - 3 * melds.length;
                    const states = [
                        { drawn: false, hand: full - 1 },
                        { drawn: true, hand: full },
                        { drawn: false, hand: full },
                    ].map((state) => JSON.stringify(stripLayout(seat, { ...state, melds }, rooms)));
                    return new Set(states).size === 1
                        ? []
                        : [`${box.width}x${box.height} ${seat} ${melds.length}`];
                }),
            );
        });
        expect(unsteady).toEqual([]);
    });
});

describe("ownMeldLayout", () => {
    const ROW = { cap: 52, gap: 10, lead: 0, ow: 68, width: 1200 };

    it("shrinks the own melds from their cap to end within the row beside the hand at its fullest, drawn tile and gap counted", () => {
        const roomy = ownMeldLayout(ROW, [CHI, CHI]);
        const { shift, tile } = ownMeldLayout({ ...ROW, width: 900 }, [CHI, CHI]);
        const handWithDrawn = 8 * ROW.ow + (7 * ROW.ow) / 60 + 0.35 * ROW.ow;
        const melds = 0.35 * ROW.ow + 2 * CHI.units * tile + ROW.gap + 2;

        expect({
            fits: handWithDrawn + melds <= 900,
            roomy: roomy.tile,
            shift,
            shrunk: tile < ROW.cap,
        }).toEqual({
            fits: true,
            roomy: ROW.cap,
            shift: 0,
            shrunk: true,
        });
    });

    it("steps the hand back into its lead only for melds at the face floor", () => {
        const melds = [OPEN_KAN, OPEN_KAN, OPEN_KAN, OPEN_KAN];
        const { shift, tile } = ownMeldLayout(
            { ...ROW, cap: 24, lead: 40, ow: 40, width: 340 },
            melds,
        );

        expect({ floor: tile === FACE_FLOOR, stepped: shift > 0 && shift <= 40 }).toEqual({
            floor: true,
            stepped: true,
        });
    });
});
