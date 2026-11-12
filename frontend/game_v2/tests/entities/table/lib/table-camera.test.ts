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
];

const PHONE_BOXES = PHONES.map(([shape, box]) => [shape, box] as const);

const SHORT_PHONE: BoardBox = { height: 275, width: 808 };

const SEATS = ["bottom", "right", "top", "left"] as const;

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

/** A plate's box from its place: its right edge there for the top and left seats, its left edge for the others. */
function plateBox(
    { left, top }: { readonly left: number; readonly top: number },
    {
        height,
        seat,
        width,
    }: { readonly height: number; readonly seat: string; readonly width: number },
): BoardRect {
    const reachesLeft = seat === "top" || seat === "left";
    return {
        bottom: top + height,
        left: reachesLeft ? left - width : left,
        right: reachesLeft ? left : left + width,
        top,
    };
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

    it("changes its tilt by at most 8 degrees between neighbouring desktop windows", () => {
        const widths = [800, 960, 1120, 1280, 1440, 1600, 1760, 1920, 2080, 2240, 2400, 2560];
        const heights = [540, 660, 780, 900, 1020, 1140, 1260, 1380, 1440];
        const tilts = heights.map((height) =>
            widths.map((width) => viewOf({ height, width }).view.camera.tilt),
        );
        const jumps = tilts.flatMap((row, down) =>
            row.flatMap((tilt, across) =>
                [row[across + 1], tilts[down + 1]?.[across]]
                    .filter((next) => next !== undefined)
                    .map((next) => Math.abs((next ?? tilt) - tilt)),
            ),
        );

        expect(Math.max(...jumps)).toBeLessThanOrEqual(8);
        expect(tilts.flat()).not.toContain(0);
    });

    it.each(DESKTOPS)(
        "opens both felt bands at most 0.75 river tiles wider than the flat ones and the top margin no wider on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const allowance = 0.75 * (screen.lengths["rw"] ?? 0);
            const shown = shownBands(view);
            const flat = flatBands(screen);

            expect(shownPiece(view, "strip-top").top).toBeCloseTo(view.margin, 0);
            expect(view.margin).toBeLessThanOrEqual(allowance);
            expect(shown.top).toBeGreaterThanOrEqual(Math.min(flat.top, 4) - 0.5);
            expect(shown.top).toBeLessThanOrEqual(Math.max(flat.top, 0) + allowance);
            expect(shown.bottom).toBeGreaterThan(0);
            expect(shown.bottom).toBeLessThanOrEqual(Math.max(flat.bottom, 0) + allowance);
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
        "draws each piece's corners where the camera shows them on %s",
        (_shape, box) => {
            const { view } = viewOf(box);
            const tilted = TABLE_PIECES.filter((piece) =>
                pieceTransform(view, piece).startsWith("matrix3d"),
            );
            for (const piece of tilted) {
                const rect = view.pieces[piece];
                const shift = view.shifts[piece];
                const far = { left: rect.right - rect.left, top: rect.bottom - rect.top };
                const [drawnLeft, drawnTop] = applied(
                    pieceTransform(view, piece),
                    far.left,
                    far.top,
                );
                const shown = projectPoint(view.camera, {
                    left: rect.right + shift.left,
                    top: rect.bottom + shift.top,
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
        "centres each plate on its anchor's height, clear of the rivers' reach (10px on a desktop, 4 on a phone), on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const height = screen.lengths["badge-h"] ?? 0;
            const width = screen.lengths["plate-w"] ?? 0;
            const rivers = (
                ["river-bottom", "river-right", "river-top", "river-left"] as const
            ).map((piece) => shownPiece(view, piece));
            const least = screen.family === "phone" ? 4 : 10;
            const gaps = SEATS.flatMap((seat) => {
                const plate = plateBox(platePlace(view, screen, seat), { height, seat, width });
                return rivers.map((river) => gapBetween(plate, river));
            });

            expect(Math.min(...gaps)).toBeGreaterThanOrEqual(least);
        },
    );
});
