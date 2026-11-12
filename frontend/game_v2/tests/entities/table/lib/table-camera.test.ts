import { describe, expect, it } from "vitest";

import { TILE_ASPECT } from "@/entities/table/lib/board-constants";
import { type BoardBox, type BoardRect, boardGeometry } from "@/entities/table/lib/board-geometry";
import {
    TABLE_PIECES,
    apparentRiver,
    farthestFace,
    flatBands,
    nearRiver,
    pieceTransform,
    platePlace,
    projectPoint,
    scalesAt,
    shownBands,
    shownPiece,
    stickUnder,
    tableView,
} from "@/entities/table/lib/table-camera";

const NO_EDGES = { bottom: 0, left: 0, right: 0, top: 0 };

const WIDE: readonly (readonly [string, BoardBox])[] = [
    ["a 2560x1440 window", { height: 1440, width: 2560 }],
    ["a 1440x900 window", { height: 900, width: 1440 }],
    ["a 1280x800 window", { height: 800, width: 1280 }],
    ["a laptop's 1366x657 window", { height: 657, width: 1366 }],
    ["a 1840x1380 window", { height: 1380, width: 1840 }],
];

const WIDTH_BOUND: readonly (readonly [string, BoardBox])[] = [
    ["a 1024x768 window", { height: 768, width: 1024 }],
    ["an 800x600 window", { height: 600, width: 800 }],
    ["a 1000x1000 window", { height: 1000, width: 1000 }],
];

const DESKTOPS = [...WIDE, ...WIDTH_BOUND];

const PHONES: readonly (readonly [string, BoardBox, number])[] = [
    ["a 667x375 phone", { height: 375, width: 667 }, 15],
    ["an 844x390 phone", { height: 390, width: 844 }, 15],
    ["an A25's board with Chrome's bars", { height: 331, width: 891 }, 12],
    ["an iPhone Plus's 736x414", { height: 414, width: 736 }, 15],
    ["a 640x400 phone", { height: 400, width: 640 }, 15],
    ["an 800x500 phone", { height: 500, width: 800 }, 15],
];

const PHONE_BOXES = PHONES.map(([shape, box]) => [shape, box] as const);

const SHORT_PHONE: BoardBox = { height: 275, width: 808 };

function viewOf(box: BoardBox): {
    readonly screen: ReturnType<typeof boardGeometry>;
    readonly view: ReturnType<typeof tableView>;
} {
    const input = {
        appliedEdges: NO_EDGES,
        box,
        safeInsets: NO_EDGES,
        slots: { band: "play" as const },
    };
    const screen = boardGeometry(input);
    return { screen, view: tableView(input, screen) };
}

function gapBetween(first: BoardRect, second: BoardRect): number {
    return Math.max(
        first.left - second.right,
        second.left - first.right,
        first.top - second.bottom,
        second.top - first.bottom,
    );
}

/** Where a CSS `matrix3d` (column-major) sends a point of its element's box. */
function applied(matrix: string, left: number, top: number): readonly [number, number] {
    const values = (/matrix3d\((?<list>[^)]*)\)/u.exec(matrix)?.groups?.list ?? "")
        .split(",")
        .map(Number);
    function at(index: number): number {
        return values[index] ?? 0;
    }
    const weight = at(3) * left + at(7) * top + at(15);
    return [
        (at(0) * left + at(4) * top + at(12)) / weight,
        (at(1) * left + at(5) * top + at(13)) / weight,
    ];
}

describe("tableView", () => {
    it.each(DESKTOPS)(
        "settles its plane solve and tilts between 10 and 20 degrees on %s",
        (_shape, box) => {
            const { view } = viewOf(box);

            expect(view.converged).toBe(true);
            expect(view.camera.tilt).toBeGreaterThanOrEqual(10);
            expect(view.camera.tilt).toBeLessThanOrEqual(20);
        },
    );

    it.each(PHONES)("tilts %s %i degrees", (_shape, box, tilt) => {
        expect(viewOf(box).view.camera.tilt).toBe(tilt);
    });

    it("keeps a phone flat where its river tile is already at the face floor", () => {
        expect(viewOf(SHORT_PHONE).view.camera.tilt).toBe(0);
    });

    it("changes its tilt by at most 8 degrees and its top margin by at most 12px between desktop windows 40x20 apart", () => {
        const widths = Array.from({ length: 45 }, (_unused, index) => 800 + 40 * index);
        const heights = Array.from({ length: 46 }, (_unused, index) => 540 + 20 * index);
        const views = heights.map((height) =>
            widths.map((width) => viewOf({ height, width }).view),
        );
        const steps = views.flatMap((row, down) =>
            row.flatMap((view, across) =>
                [row[across + 1], views[down + 1]?.[across]].flatMap((next) =>
                    next === undefined
                        ? []
                        : [
                              {
                                  margin: Math.abs(next.margin - view.margin),
                                  tilt: Math.abs(next.camera.tilt - view.camera.tilt),
                              },
                          ],
                ),
            ),
        );

        expect(Math.max(...steps.map(({ tilt }) => tilt))).toBeLessThanOrEqual(8);
        expect(Math.max(...steps.map(({ margin }) => margin))).toBeLessThanOrEqual(12);
        expect(views.flat().map((view) => view.camera.tilt)).not.toContain(0);
    });

    it.each(DESKTOPS)(
        "keeps both felt bands between the flat ones and 0.75 river tiles wider, its top margin under 0.15, on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const rw = screen.lengths["rw"] ?? 0;
            const shown = shownBands(view);
            const flat = flatBands(screen);

            expect(shownPiece(view, "strip-top").top).toBeCloseTo(view.margin, 0);
            expect(view.margin).toBeLessThanOrEqual(0.15 * rw + 0.5);
            expect(shown.top).toBeGreaterThanOrEqual(flat.top - 1);
            expect(shown.top).toBeLessThanOrEqual(Math.max(flat.top, 0) + 0.75 * rw + 0.5);
            expect(shown.bottom).toBeGreaterThanOrEqual(Math.min(flat.bottom, 4) - 0.5);
            expect(shown.bottom).toBeLessThanOrEqual(Math.max(flat.bottom, 0) + 0.75 * rw + 0.5);
        },
    );

    it.each(DESKTOPS)(
        "shows the core's middle river tile within 5% of the flat one, farther tiles smaller, the own tile the largest, on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const flatRiver = screen.lengths["rw"] ?? 0;
            function at(top: number): number {
                return scalesAt(view.camera, top).across;
            }

            expect(Math.abs(apparentRiver(view) - flatRiver)).toBeLessThanOrEqual(
                0.05 * flatRiver + 0.5,
            );
            expect(at(view.pieces["strip-top"].top)).toBeLessThan(at(view.pieces["river-top"].top));
            expect(at(view.pieces["river-top"].top)).toBeLessThan(
                at(view.pieces["river-bottom"].bottom),
            );
            expect(at(view.pieces["strip-left"].top)).toBeLessThan(
                at(view.pieces["strip-left"].bottom),
            );
            expect(nearRiver(view)).toBeLessThanOrEqual(0.85 * (screen.lengths["ow"] ?? 0) + 0.5);
        },
    );

    it.each([...DESKTOPS, ...PHONE_BOXES])(
        "shows its farthest faces at the face floor on %s",
        (_shape, box) => {
            const face = farthestFace(viewOf(box).view);

            expect(face.short).toBeGreaterThanOrEqual(13 - 0.01);
            expect(face.long).toBeGreaterThanOrEqual(13 * TILE_ASPECT - 0.01);
        },
    );

    it.each([...DESKTOPS, ...PHONE_BOXES])(
        "draws all four corners of every tilted piece where the camera shows them on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const tilted = TABLE_PIECES.filter((piece) =>
                pieceTransform(view, piece).startsWith("matrix3d"),
            );
            const flatCounters = screen.family === "phone" ? ["dora"] : [];
            expect(tilted).toStrictEqual(
                TABLE_PIECES.filter((piece) => !flatCounters.includes(piece)),
            );
            const corners = tilted.flatMap((piece) => {
                const rect = view.pieces[piece];
                return [
                    [0, 0],
                    [rect.right - rect.left, 0],
                    [0, rect.bottom - rect.top],
                    [rect.right - rect.left, rect.bottom - rect.top],
                ].map(([left = 0, top = 0]) => ({ left, piece, rect, top }));
            });
            for (const { left, piece, rect, top } of corners) {
                const [drawnLeft, drawnTop] = applied(pieceTransform(view, piece), left, top);
                const shown = projectPoint(view.camera, {
                    left: rect.left + view.shifts[piece].left + left,
                    top: rect.top + view.shifts[piece].top + top,
                });
                expect(rect.left + drawnLeft).toBeCloseTo(shown.left, 3);
                expect(rect.top + drawnTop - view.tableTop).toBeCloseTo(shown.top, 3);
            }
        },
    );

    it.each(DESKTOPS)(
        "keeps the counters clear of the strips and the side strips on the plane, short of the own row, on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const dora = shownPiece(view, "dora");
            const ownRowTop = screen.lengths["foreground-top"] ?? 0;

            expect(gapBetween(view.pieces.dora, view.pieces["strip-top"])).toBeGreaterThanOrEqual(
                2,
            );
            expect(gapBetween(dora, shownPiece(view, "strip-left"))).toBeGreaterThanOrEqual(2);
            expect(shownPiece(view, "strip-left").bottom).toBeLessThanOrEqual(ownRowTop + 0.5);
            expect(shownPiece(view, "strip-right").bottom).toBeLessThanOrEqual(ownRowTop + 0.5);
        },
    );

    it.each([...DESKTOPS, ...PHONE_BOXES])(
        "keeps a top row plate's riichi stick 10px off the core under it on a desktop, 6 on a phone, on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const core = (["centre", "river-left", "river-right", "river-top"] as const).map(
                (piece) => shownPiece(view, piece),
            );
            const least = screen.family === "phone" ? 6 : 10;
            const gaps = (["top", "right"] as const).flatMap((seat) => {
                const { left, top } = platePlace(view, screen, seat);
                const stick = stickUnder(screen, { left, seat, top });
                return core
                    .filter((piece) => piece.left < stick.right && stick.left < piece.right)
                    .filter((piece) => piece.bottom > stick.foot)
                    .map((piece) => piece.top - stick.foot);
            });

            expect(Math.min(Infinity, ...gaps)).toBeGreaterThanOrEqual(least - 0.01);
        },
    );
});
