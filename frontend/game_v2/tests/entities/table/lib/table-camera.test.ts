import { describe, expect, it } from "vitest";

import { type BoardBox, boardGeometry } from "@/entities/table/lib/board-geometry";
import {
    TABLE_PIECES,
    showPiecePoint,
    shownPiece,
    tableView,
} from "@/entities/table/lib/table-camera";

const NO_EDGES = { bottom: 0, left: 0, right: 0, top: 0 };

const SHAPES: readonly (readonly [string, BoardBox])[] = [
    ["a 2560x1440 window", { height: 1420, width: 2540 }],
    ["a 1440x900 window", { height: 880, width: 1420 }],
    ["a 1280x800 window", { height: 780, width: 1260 }],
    ["a 1024x768 window", { height: 748, width: 1004 }],
    ["a laptop's 1366x657 window", { height: 637, width: 1346 }],
    ["an iPhone 11 with Safari's bars", { height: 275, width: 808 }],
];

function geometryOf(box: BoardBox): ReturnType<typeof boardGeometry> {
    return boardGeometry({
        appliedEdges: NO_EDGES,
        box,
        safeInsets: NO_EDGES,
        slots: { band: "play" },
    });
}

describe("tableView", () => {
    it.each(SHAPES)(
        "keeps the top strip's far edge where the flat board lays it on %s",
        (_shape, box) => {
            const view = tableView(geometryOf(box));

            expect(shownPiece(view, "strip-top").top).toBeCloseTo(view.pieces["strip-top"].top, 1);
        },
    );

    it.each(SHAPES)(
        "keeps every tilted piece on the board and short of the own row's top on %s",
        (_shape, box) => {
            const geometry = geometryOf(box);
            const view = tableView(geometry);
            const ownRowTop = geometry.lengths["foreground-top"] ?? 0;

            for (const piece of TABLE_PIECES) {
                const shown = shownPiece(view, piece);
                expect(shown.top).toBeGreaterThanOrEqual(view.pieces[piece].top - 0.5);
                expect(shown.bottom).toBeLessThanOrEqual(ownRowTop + 0.5);
            }
            expect(shownPiece(view, "strip-left").left).toBeCloseTo(
                view.pieces["strip-left"].left,
                1,
            );
            expect(shownPiece(view, "strip-right").right).toBeCloseTo(
                view.pieces["strip-right"].right,
                1,
            );
        },
    );

    it.each(SHAPES)(
        "shows the river tile at the screen solve's width across the core's middle on %s",
        (_shape, box) => {
            const geometry = geometryOf(box);
            const view = tableView(geometry);
            const rw = geometry.lengths["rw"] ?? 0;
            const { anchor } = view.poses.core;
            const start = showPiecePoint(view, "core", anchor);
            const end = showPiecePoint(view, "core", { left: anchor.left + rw, top: anchor.top });

            expect(end.left - start.left).toBeCloseTo(rw, 1);
            expect(start.left).toBeCloseTo(anchor.left, 1);
            expect(start.top).toBeCloseTo(anchor.top, 1);
        },
    );
});
