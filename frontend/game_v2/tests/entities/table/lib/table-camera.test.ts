import { describe, expect, it } from "vitest";

import { type BoardBox, type BoardRect, boardGeometry } from "@/entities/table/lib/board-geometry";
import { shownPiece, tableView } from "@/entities/table/lib/table-camera";

const NO_EDGES = { bottom: 0, left: 0, right: 0, top: 0 };

const DESKTOPS: readonly (readonly [string, BoardBox])[] = [
    ["a 2560x1440 window", { height: 1420, width: 2540 }],
    ["a 1440x900 window", { height: 880, width: 1420 }],
    ["a 1280x800 window", { height: 780, width: 1260 }],
    ["a 1024x768 window", { height: 748, width: 1004 }],
    ["an 800x600 window", { height: 580, width: 780 }],
    ["a laptop's 1366x657 window", { height: 637, width: 1346 }],
];

const PHONES: readonly (readonly [string, BoardBox])[] = [
    ["an iPhone 11 with Safari's bars", { height: 275, width: 808 }],
    ["a 667x375 phone", { height: 375, width: 667 }],
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

function gapBetween(first: BoardRect, second: BoardRect): number {
    return Math.max(
        first.left - second.right,
        second.left - first.right,
        first.top - second.bottom,
        second.top - first.bottom,
    );
}

describe("tableView", () => {
    it.each([...DESKTOPS, ...PHONES])("settles its plane solve on %s", (_shape, box) => {
        expect(viewOf(box).view.converged).toBe(true);
    });

    it.each(DESKTOPS)(
        "tilts a desktop's table and fills the board from its top on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const tableHeight = screen.lengths["table-h"];

            expect(view.camera.tilt).toBeGreaterThan(0);
            expect(shownPiece(view, "strip-top").top + view.tableTop).toBeCloseTo(0, 0);
            if (tableHeight !== undefined) {
                expect(view.tableTop + tableHeight).toBeCloseTo(screen.box.height, 0);
            }
        },
    );

    it.each(DESKTOPS)("shows farther pieces smaller under its one camera on %s", (_shape, box) => {
        const { maps } = viewOf(box).view;

        expect(maps["strip-top"].scale).toBeLessThan(maps["river-top"].scale);
        expect(maps["river-top"].scale).toBeLessThan(maps.centre.scale);
        expect(maps.centre.scale).toBeLessThan(maps["river-bottom"].scale);
    });

    it.each(DESKTOPS)(
        "keeps the counters clear of the strips and a desktop's side strips short of the own row on %s",
        (_shape, box) => {
            const { screen, view } = viewOf(box);
            const dora = shownPiece(view, "dora");
            const ownRowTop = screen.lengths["foreground-top"] ?? 0;

            expect(gapBetween(dora, shownPiece(view, "strip-top"))).toBeGreaterThanOrEqual(2);
            expect(gapBetween(dora, shownPiece(view, "strip-left"))).toBeGreaterThanOrEqual(2);
            expect(shownPiece(view, "strip-left").bottom).toBeLessThanOrEqual(ownRowTop + 0.5);
            expect(shownPiece(view, "strip-right").bottom).toBeLessThanOrEqual(ownRowTop + 0.5);
        },
    );

    it.each(PHONES)(
        "keeps a phone's table flat where its melds sit at the face floor on %s",
        (_shape, box) => {
            expect(viewOf(box).view.camera.tilt).toBe(0);
        },
    );
});
