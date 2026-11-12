import { describe, expect, it } from "vitest";

import { TILE_ASPECT } from "@/entities/table/lib/board-constants";
import { type BoardBox, type BoardRect, boardGeometry } from "@/entities/table/lib/board-geometry";
import {
    farthestFace,
    flatBands,
    nearRiver,
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
];

const WIDTH_BOUND: readonly (readonly [string, BoardBox])[] = [
    ["a 1024x768 window", { height: 768, width: 1024 }],
    ["an 800x600 window", { height: 600, width: 800 }],
    ["a 1000x1000 window", { height: 1000, width: 1000 }],
];

const PHONES: readonly (readonly [string, BoardBox])[] = [
    ["a 667x375 phone", { height: 375, width: 667 }],
    ["an 844x390 phone", { height: 390, width: 844 }],
];

const SHORT_PHONE: readonly [string, BoardBox] = [
    "an iPhone 11's board with Safari's bars",
    { height: 275, width: 808 },
];

const DESKTOPS = [...WIDE, ...WIDTH_BOUND];

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

describe("tableView", () => {
    it.each([...DESKTOPS, ...PHONES])("settles its plane solve and tilts on %s", (_shape, box) => {
        const { view } = viewOf(box);

        expect(view.converged).toBe(true);
        expect(view.camera.tilt).toBeGreaterThan(0);
    });

    it.each(DESKTOPS)(
        "shows the table's top where the flat table's stands, with no band wider than the flat one's by 0.75 river tiles, on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const rw = screen.lengths["rw"] ?? 0;
            const shown = shownBands(view);
            const flat = flatBands(screen);

            expect(shownPiece(view, "strip-top").top).toBeCloseTo(0, 0);
            expect(shown.top).toBeLessThanOrEqual(Math.max(flat.top, 0) + 0.75 * rw);
            expect(shown.bottom).toBeLessThanOrEqual(Math.max(flat.bottom, 0) + 0.75 * rw);
        },
    );

    it.each(WIDE)("fills a wide window's board from its top edge on %s", (_shape, box) => {
        expect(viewOf(box).view.tableTop).toBe(0);
    });

    it.each(DESKTOPS)(
        "shows farther tiles smaller and keeps the own tile the largest on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            function at(top: number): number {
                return scalesAt(view.camera, top).across;
            }

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

    it.each([...DESKTOPS, ...PHONES])(
        "shows its farthest faces at the face floor on %s",
        (_shape, box) => {
            const face = farthestFace(viewOf(box).view);

            expect(face.short).toBeGreaterThanOrEqual(13 - 0.01);
            expect(face.long).toBeGreaterThanOrEqual(13 * TILE_ASPECT - 0.01);
        },
    );

    it.each(DESKTOPS)(
        "keeps the counters clear of the strips and a desktop's side strips short of the own row on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const dora = shownPiece(view, "dora");
            const ownRowTop = screen.lengths["foreground-top"] ?? 0;

            expect(gapBetween(view.pieces.dora, view.pieces["strip-top"])).toBeGreaterThanOrEqual(
                2,
            );
            expect(view.shifts.dora).toStrictEqual(view.shifts["strip-top"]);
            expect(gapBetween(dora, shownPiece(view, "strip-left"))).toBeGreaterThanOrEqual(2);
            expect(shownPiece(view, "strip-left").bottom).toBeLessThanOrEqual(ownRowTop + 0.5);
            expect(shownPiece(view, "strip-right").bottom).toBeLessThanOrEqual(ownRowTop + 0.5);
        },
    );

    it("keeps a phone flat where its side strips beside the own row have no room to grow", () => {
        expect(viewOf(SHORT_PHONE[1]).view.camera.tilt).toBe(0);
    });

    it.each([...DESKTOPS, ...PHONES, SHORT_PHONE])(
        "keeps the side strips clear of the own row beside them on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const own = screen.areas.hand ?? { bottom: 0, left: 0, right: 0, top: Infinity };
            const left = shownPiece(view, "strip-left");
            const right = shownPiece(view, "strip-right");

            expect(left.bottom <= own.top || left.right <= own.left).toBe(true);
            expect(right.bottom <= own.top || right.left >= own.right).toBe(true);
        },
    );

    it.each(PHONES)(
        "lays a phone's tilted river tile no smaller than the flat one on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);

            expect(view.plane.lengths["rw"] ?? 0).toBeGreaterThanOrEqual(screen.lengths["rw"] ?? 0);
        },
    );
});
