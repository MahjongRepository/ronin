import { describe, expect, it } from "vitest";

import {
    SIDEWAYS_UNITS,
    STACKED_DEPTH,
    TILE_ASPECT,
    TILE_EDGE_SHARE,
    TOP_HAND_EDGE_SHARE,
} from "@/entities/table/lib/board-constants";
import {
    type BoardBox,
    type BoardGeometry,
    type BoardRect,
    boardGeometry,
    phonePromptHeight,
} from "@/entities/table/lib/board-geometry";
import { stripLayout } from "@/entities/table/lib/strip-layout";
import {
    TABLE_PIECES,
    type TableView,
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
    surfaceViewValues,
    tablePieces,
    tableView,
    viewAt,
} from "@/entities/table/lib/table-camera";
import { tileBody } from "@/entities/tile";

const NO_EDGES = { bottom: 0, left: 0, right: 0, top: 0 };

const WIDE: readonly (readonly [string, BoardBox])[] = [
    ["a 2560x1440 window", { height: 1440, width: 2560 }],
    ["a 1440x900 window", { height: 900, width: 1440 }],
    ["a 1280x800 window", { height: 800, width: 1280 }],
    ["a laptop's 1366x657 window", { height: 657, width: 1366 }],
    ["a 1840x1380 window", { height: 1380, width: 1840 }],
    ["a tall 1680x1220 window", { height: 1220, width: 1680 }],
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
    ["an A25's board with Chrome's bars", { height: 331, width: 891 }, 15],
    ["an iPhone Plus's 736x414", { height: 414, width: 736 }, 15],
    ["a 640x400 phone", { height: 400, width: 640 }, 15],
    ["an 800x500 phone", { height: 500, width: 800 }, 15],
];

const PHONE_BOXES = PHONES.map(([shape, box]) => [shape, box] as const);

const SHORT_PHONE: BoardBox = { height: 275, width: 808 };

const SEATS = ["bottom", "right", "top", "left"] as const;

const ADDED_KAN = { depth: STACKED_DEPTH, units: 2 + SIDEWAYS_UNITS };

/** Phones whose rounds settled slowly: the core rises over several rounds at 15 degrees. */
const SLOW_PHONES: readonly BoardBox[] = [
    { height: 340, width: 850 },
    { height: 340, width: 900 },
];

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

const GRID_WIDTHS = Array.from({ length: 45 }, (_unused, index) => 800 + 40 * index);

const GRID_HEIGHTS = Array.from({ length: 46 }, (_unused, index) => 540 + 20 * index);

/** The desktop windows 40x20 apart from 800x540 to 2560x1440, a row per height, solved once for the tests that walk them. */
const desktopGrid = (() => {
    let rows: readonly (readonly ReturnType<typeof tableView>[])[] | null = null;
    return (): readonly (readonly ReturnType<typeof tableView>[])[] => {
        rows ??= GRID_HEIGHTS.map((height) =>
            GRID_WIDTHS.map((width) => viewOf({ height, width }).view),
        );
        return rows;
    };
})();

/** A table seen flat or through its camera: where it shows a plane point, its pieces and their moves. */
interface Seen {
    readonly show: (point: { left: number; top: number }) => { left: number; top: number };
    readonly pieces: ReturnType<typeof tableView>["pieces"];
    readonly shifts: Partial<ReturnType<typeof tableView>["shifts"]>;
    readonly rw: number;
    readonly counters: BoardRect;
    /** How far in from the top strip's box its line, and so its melds, start. */
    readonly inset: number;
}

function flatOf(screen: BoardGeometry): Seen {
    const pieces = tablePieces(screen);
    return {
        counters: pieces.dora,
        inset: 0,
        pieces,
        rw: screen.lengths["rw"] ?? 0,
        shifts: {},
        show: (point) => point,
    };
}

function seenOf(view: ReturnType<typeof tableView>): Seen {
    return {
        counters: shownPiece(view, "dora"),
        inset: view.plane.strips?.top.inset ?? 0,
        pieces: view.pieces,
        rw: view.plane.lengths["rw"] ?? 0,
        shifts: view.shifts,
        show: (point) => projectPoint(view.camera, point),
    };
}

/**
 * The gaps the camera shows between the top strip's end tiles (at its stacked depth) and each side strip's farthest
 * tile (on its lane's outer edge, a tile's length deep), and between the counters and the strip's first tile.
 */
function endGaps(
    table: ReturnType<typeof tableView> | Seen,
): Readonly<Record<"counters" | "left" | "right", number>> {
    const { counters, inset, pieces, rw, shifts, show } = "camera" in table ? seenOf(table) : table;
    const strip = pieces["strip-top"];
    const deep = (TILE_ASPECT + TILE_EDGE_SHARE) * rw;
    function gap(seat: "strip-left" | "strip-right"): number {
        const left = seat === "strip-left";
        const foot = show({ left: left ? strip.left + inset : strip.right, top: strip.bottom });
        const side = pieces[seat];
        const shift = shifts[seat] ?? { left: 0, top: 0 };
        const corner = show({
            left: (left ? side.left + deep : side.right - deep) + shift.left,
            top: side.top + shift.top,
        });
        return Math.max(
            left ? foot.left - corner.left : corner.left - foot.left,
            corner.top - foot.top,
        );
    }
    const first = show({ left: strip.left + inset, top: strip.bottom }).left;
    return { counters: first - counters.right, left: gap("strip-left"), right: gap("strip-right") };
}

/** A plate's pill from its place, its box's width: its right edge there for the top and left seats, its left edge for the others. */
function platePill(
    screen: BoardGeometry,
    view: ReturnType<typeof tableView>,
    seat: (typeof SEATS)[number],
): BoardRect {
    const { left, top } = platePlace(view, screen, seat);
    const width = screen.lengths["plate-w"] ?? 0;
    const pill = screen.lengths["pill-h"] ?? 0;
    const pillTop = top + ((screen.lengths["badge-h"] ?? 0) - pill) / 2;
    const reachesLeft = seat === "top" || seat === "left";
    return {
        bottom: pillTop + pill,
        left: reachesLeft ? left - width : left,
        right: reachesLeft ? left : left + width,
        top: pillTop,
    };
}

/** How low the top strip's added kan draws its foot (its edge under it) on a geometry, laid by its strip rooms. */
function addedKanFoot(geometry: BoardGeometry, stripTop: number): number {
    if (geometry.strips === null) {
        throw new Error("The board has no strip rooms");
    }
    const content = { drawn: true, hand: 11, melds: [ADDED_KAN] };
    const [meld] = stripLayout("top", content, geometry.strips).melds;
    const tile = meld?.tile ?? 0;
    return stripTop + (STACKED_DEPTH + TILE_EDGE_SHARE) * tile;
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

function appliedFlat(matrix: string, left: number, top: number): readonly [number, number] {
    const [acrossX = 0, acrossY = 0, downX = 0, downY = 0, moveX = 0, moveY = 0] = (
        /^matrix\((?<list>[^)]*)\)$/u.exec(matrix)?.groups?.list ?? ""
    )
        .split(",")
        .map(Number);
    return [acrossX * left + downX * top + moveX, acrossY * left + downY * top + moveY];
}

function flatCentreCorners(view: TableView): readonly { left: number; top: number }[] {
    const { centre } = view.pieces;
    const [width, height] = [centre.right - centre.left, centre.bottom - centre.top];
    return [
        [0, 0],
        [width, 0],
        [0, height],
        [width, height],
    ].map(([left = 0, top = 0]) => {
        const [drawnLeft, drawnTop] = appliedFlat(pieceTransform(view, "centre"), left, top);
        return {
            left: centre.left + drawnLeft,
            top: centre.top + drawnTop - view.tableTop,
        };
    });
}

function expectCentreFlatInsideItsQuad(view: TableView): void {
    const { centre } = view.pieces;
    const quad = shownPiece(view, "centre");
    const [farLeft, , nearLeft, nearRight] = flatCentreCorners(view);
    const shownFarLeft = projectPoint(view.camera, {
        left: centre.left + view.shifts.centre.left,
        top: centre.top + view.shifts.centre.top,
    });
    expect(farLeft).toStrictEqual({
        left: expect.closeTo(shownFarLeft.left, 3),
        top: expect.closeTo(shownFarLeft.top, 3),
    });
    const outsideQuad = flatCentreCorners(view).filter(
        ({ left, top }) =>
            left < quad.left - 0.001 ||
            left > quad.right + 0.001 ||
            top < quad.top - 0.001 ||
            top > quad.bottom + 0.001,
    );
    expect(outsideQuad).toStrictEqual([]);
    expect((nearRight?.left ?? 0) - (nearLeft?.left ?? 0)).toBeGreaterThan(
        (quad.right - quad.left) * 0.9,
    );
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

    it.each(DESKTOPS)(
        "keeps both felt bands between the flat ones and 0.95 river tiles wider, its top margin under 0.15, on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const rw = screen.lengths["rw"] ?? 0;
            const shown = shownBands(view);
            const flat = flatBands(screen);

            expect(shownPiece(view, "strip-top").top).toBeCloseTo(view.margin, 0);
            expect(view.margin).toBeLessThanOrEqual(0.15 * rw + 0.5);
            expect(shown.top).toBeGreaterThanOrEqual(flat.top - 1);
            expect(shown.top).toBeLessThanOrEqual(Math.max(flat.top, 0) + 0.95 * rw + 0.5);
            expect(shown.bottom).toBeGreaterThanOrEqual(Math.min(flat.bottom, 4) - 0.5);
            expect(shown.bottom).toBeLessThanOrEqual(Math.max(flat.bottom, 0) + 0.95 * rw + 0.5);
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
        "draws all four corners of every tilted piece where the camera shows them, the centre flat inside its quad, on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const tilted = TABLE_PIECES.filter((piece) =>
                pieceTransform(view, piece).startsWith("matrix3d"),
            );
            expect(tilted).toStrictEqual(
                TABLE_PIECES.filter(
                    (piece) =>
                        piece !== "centre" && (screen.family !== "phone" || piece !== "dora"),
                ),
            );
            expectCentreFlatInsideItsQuad(view);
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
});

describe("tableView on desktop windows 40x20 apart", () => {
    it("changes its tilt by at most 8 degrees and its top margin by at most 12px between neighbours", () => {
        const views = desktopGrid();
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

    it("shows every table piece whole on the board", () => {
        const outside = desktopGrid().flatMap((row, down) =>
            row.flatMap((view, across) => {
                const box = { height: GRID_HEIGHTS[down] ?? 0, width: GRID_WIDTHS[across] ?? 0 };
                return TABLE_PIECES.filter((piece) => {
                    const shown = shownPiece(view, piece);
                    return (
                        shown.left < -0.5 ||
                        shown.right > box.width + 0.5 ||
                        shown.top + view.tableTop < -0.5 ||
                        shown.bottom + view.tableTop > box.height + 0.5
                    );
                }).map((piece) => `${piece} at ${box.width}x${box.height}`);
            }),
        );

        expect(outside).toStrictEqual([]);
    });

    it("shows the side strips' farthest tiles 16px or the flat gap off the top strip's end tiles, the counters 8px or the flat gap off its first", () => {
        const short = desktopGrid().flatMap((row, down) =>
            row.flatMap((view, across) => {
                const box = { height: GRID_HEIGHTS[down] ?? 0, width: GRID_WIDTHS[across] ?? 0 };
                const { screen } = viewOf(box);
                const tilted = endGaps(view);
                const flat = endGaps(flatOf(screen));
                const planeCounters = view.pieces["strip-top"].left - view.pieces.dora.right;
                return [
                    tilted.left >= Math.min(16, flat.left) - 0.5 ? "" : "left",
                    tilted.right >= Math.min(16, flat.right) - 0.5 ? "" : "right",
                    tilted.counters >= Math.max(8, Math.min(flat.counters, planeCounters)) - 0.5
                        ? ""
                        : "counters",
                ]
                    .filter((name) => name !== "")
                    .map((name) => `${name} at ${box.width}x${box.height}`);
            }),
        );

        expect(short).toStrictEqual([]);
    });
});

describe("tableView's plates", () => {
    it.each([...DESKTOPS, ...PHONE_BOXES])(
        "keeps all four plates' pills 4px off the core on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const core = (
                ["centre", "river-bottom", "river-left", "river-right", "river-top"] as const
            ).map((piece) => shownPiece(view, piece));
            const gaps = SEATS.flatMap((seat) =>
                core.map((piece) => gapBetween(platePill(screen, view, seat), piece)),
            );

            expect(Math.min(...gaps)).toBeGreaterThanOrEqual(4 - 0.01);
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
            const gaps = (["top", "right"] as const).map((seat) => {
                const { left, top } = platePlace(view, screen, seat);
                const stick = stickUnder(screen, { left, seat, top });
                return core
                    .filter((piece) => piece.left < stick.right && stick.left < piece.right)
                    .filter((piece) => piece.bottom > stick.foot)
                    .map((piece) => piece.top - stick.foot);
            });

            for (const seatGaps of gaps) {
                expect(seatGaps).not.toStrictEqual([]);
                expect(Math.min(...seatGaps)).toBeGreaterThanOrEqual(least - 0.01);
            }
        },
    );
});

function topBackFoot(view: TableView, left: number): number {
    const back = tileBody({
        end: "shown",
        lay: "standing",
        material: "back",
        sideways: false,
        turn: 180,
    });
    const depth = (back.top + back.edge) * (view.plane.lengths["rw"] ?? 0);
    return projectPoint(view.camera, { left, top: view.pieces["strip-top"].top + depth }).top;
}

describe("tableView on phones", () => {
    it.each([...PHONE_BOXES, ["a short flat phone", SHORT_PHONE] as const])(
        "shows the top strip's added kan no nearer the top river than the flat board does, and its hand's standing backs clear of it, on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const flat = flatOf(screen);
            const strip = view.pieces["strip-top"];
            const middle = (strip.left + strip.right) / 2;
            const foot = projectPoint(view.camera, {
                left: middle,
                top: addedKanFoot(view.plane, strip.top),
            });
            const flatGap =
                flat.pieces["river-top"].top - addedKanFoot(screen, flat.pieces["strip-top"].top);
            const handGap = shownPiece(view, "river-top").top - topBackFoot(view, middle);

            expect(shownPiece(view, "river-top").top - foot.top).toBeGreaterThanOrEqual(
                flatGap - 1,
            );
            expect(handGap).toBeGreaterThan(0);
            expect(shownBands(view).top).toBeCloseTo(handGap, 5);
        },
    );

    it.each([...PHONE_BOXES.map(([, box]) => box), ...SLOW_PHONES])(
        "settles its rounds at every phone tilt on %o",
        (box) => {
            const { screen } = viewOf(box);
            const input = {
                appliedEdges: NO_EDGES,
                box,
                safeInsets: NO_EDGES,
                slots: { band: "play" as const },
            };

            for (const tilt of [15, 12, 10]) {
                expect(viewAt(input, screen, tilt).converged).toBe(true);
            }
        },
    );

    it.each(DESKTOPS)("settles its cap steps at every desktop tilt on %s", (_shape, box) => {
        const { screen } = viewOf(box);
        const input = {
            appliedEdges: NO_EDGES,
            box,
            safeInsets: NO_EDGES,
            slots: { band: "play" as const },
        };

        for (const tilt of [20, 18, 15, 12, 10]) {
            expect(viewAt(input, screen, tilt).converged).toBe(true);
        }
    });
});

function cssAffine(value: string): (left: number, top: number) => [number, number] {
    const [scaleX = 0, skewY = 0, skewX = 0, scaleY = 0, moveX = 0, moveY = 0] = value
        .replace(/^matrix\(|\)$/g, "")
        .split(",")
        .map(Number);
    return (left, top) => [
        scaleX * left + skewX * top + moveX,
        skewY * left + scaleY * top + moveY,
    ];
}

function laidStripCorner(view: TableView, left: number, top: number): [number, number] {
    const piece = view.pieces["strip-top"];
    const shift = view.shifts["strip-top"];
    const shown = projectPoint(view.camera, {
        left: piece.left + shift.left + left,
        top: piece.top + shift.top + top,
    });
    return [shown.left - piece.left, shown.top + view.tableTop - piece.top];
}

describe("the top hand", () => {
    it.each([...WIDE, PHONE_BOXES[0]])(
        "stands upright on %s: its owner's edge and its foot where the strip's camera lays them, as wide as the foot",
        (_shape, box) => {
            const { view } = viewOf(box);
            const hand = cssAffine(
                Object.fromEntries(surfaceViewValues(view))["--geo-camera-top-hand"] ?? "",
            );
            const width = view.pieces["strip-top"].right - view.pieces["strip-top"].left;
            const foot = (TILE_ASPECT + TOP_HAND_EDGE_SHARE) * (view.plane.lengths["rw"] ?? 0);

            for (const along of [0, width]) {
                const [footLeft, footTop] = laidStripCorner(view, along, foot);
                expect(hand(along, foot)[0]).toBeCloseTo(footLeft, 3);
                expect(hand(along, foot)[1]).toBeCloseTo(footTop, 3);
                expect(hand(along, 0)[1]).toBeCloseTo(laidStripCorner(view, along, 0)[1], 3);
            }
        },
    );
});

describe("tableView between the grid's windows", () => {
    it("tilts every desktop window 80x40 apart off the 40x20 grid, never flat, at most 8 degrees from its neighbours", () => {
        const widths = Array.from({ length: 22 }, (_unused, index) => 860 + 80 * index);
        const heights = Array.from({ length: 23 }, (_unused, index) => 530 + 40 * index);
        const tilts = heights.map((height) =>
            widths.map((width) => viewOf({ height, width }).view.camera.tilt),
        );
        const jumps = tilts.flatMap((row, down) =>
            row.flatMap((tilt, across) =>
                [row[across + 1], tilts[down + 1]?.[across]].flatMap((next) =>
                    next === undefined ? [] : [Math.abs(next - tilt)],
                ),
            ),
        );

        expect(tilts.flat()).not.toContain(0);
        expect(Math.max(...jumps)).toBeLessThanOrEqual(8);
    });

    it("leaves a phone 20x20 apart off the grid flat only where no tilt shows its faces at the floor", () => {
        const boxes = Array.from({ length: 10 }, (_unused, down) =>
            Array.from({ length: 15 }, (_unused2, across) => ({
                height: 305 + 20 * down,
                width: 645 + 20 * across,
            })),
        ).flat();
        const flatThoughFloored = boxes.flatMap((box) => {
            const { screen, view } = viewOf(box);
            if (screen.family !== "phone" || view.camera.tilt !== 0) {
                return [];
            }
            const input = {
                appliedEdges: NO_EDGES,
                box,
                safeInsets: NO_EDGES,
                slots: { band: "play" as const },
            };
            const floored = [15, 12, 10].filter((tilt) => {
                const face = farthestFace(viewAt(input, screen, tilt));
                return face.short >= 13 - 0.01 && face.long >= 13 * TILE_ASPECT - 0.01;
            });
            return floored.length > 0 ? [`${box.width}x${box.height}`] : [];
        });

        expect(flatThoughFloored).toStrictEqual([]);
    });

    it("never moves a phone's river tile more than 2px between neighbours 20x20 apart off the grid, 3px where the widest prompt first fits", () => {
        const widths = Array.from({ length: 15 }, (_unused, across) => 645 + 20 * across);
        const heights = Array.from({ length: 10 }, (_unused, down) => 305 + 20 * down);
        const boards = heights.map((height) =>
            widths.map((width) => {
                const { screen } = viewOf({ height, width });
                if (screen.family !== "phone") {
                    return null;
                }
                const { bottom = 0, left = 0, right = 0, top = 0 } = screen.areas["actions"] ?? {};
                return {
                    holdsPrompt:
                        bottom - top >=
                        phonePromptHeight(right - left, screen.lengths["timer-w"] ?? 0) - 0.001,
                    river: screen.lengths["rw"] ?? 0,
                };
            }),
        );
        const cliffs = boards.flatMap((row, down) =>
            row.flatMap((board, across) =>
                [
                    [row[across + 1], widths[across + 1], heights[down]] as const,
                    [boards[down + 1]?.[across], widths[across], heights[down + 1]] as const,
                ].flatMap(([next, width, height]) => {
                    if (board === null || next === null || next === undefined) {
                        return [];
                    }
                    const bound = board.holdsPrompt === next.holdsPrompt ? 2 : 3;
                    return Math.abs(next.river - board.river) <= bound
                        ? []
                        : [
                              `${widths[across]}x${heights[down]} ${board.river} -> ${width}x${height} ${next.river}`,
                          ];
                }),
            ),
        );

        expect(cliffs).toStrictEqual([]);
    });
});
