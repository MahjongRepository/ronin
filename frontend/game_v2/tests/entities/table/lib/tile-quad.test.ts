import { describe, expect, it } from "vitest";

import { boardGeometry } from "@/entities/table/lib/board-geometry";
import { pieceTransform, tableView } from "@/entities/table/lib/table-camera";
import {
    type PieceFrame,
    type ScreenPoint,
    pieceOrigin,
    quadWarp,
    rectQuad,
    tiltedQuad,
    unwarpPoint,
    warpPoint,
} from "@/entities/table/lib/tile-quad";

const NO_EDGES = { bottom: 0, left: 0, right: 0, top: 0 };

/** The 1440x900 desktop's top strip: its CSS matrix3d values and its box's size. */
function topStrip(): {
    readonly matrix: readonly number[];
    readonly width: number;
    readonly height: number;
} {
    const input = {
        appliedEdges: NO_EDGES,
        box: { height: 900, width: 1440 },
        safeInsets: NO_EDGES,
        slots: { band: "play" as const },
    };
    const view = tableView(input, boardGeometry(input));
    const values =
        /matrix3d\((?<list>[^)]*)\)/u.exec(pieceTransform(view, "strip-top"))?.groups?.list ?? "";
    const strip = view.pieces["strip-top"];
    return {
        height: strip.bottom - strip.top,
        matrix: values.split(",").map(Number),
        width: strip.right - strip.left,
    };
}

function shown({ matrix, origin }: PieceFrame, { left, top }: ScreenPoint): ScreenPoint {
    const weight = (matrix[3] ?? 0) * left + (matrix[7] ?? 0) * top + (matrix[15] ?? 1);
    return {
        left:
            origin.left +
            ((matrix[0] ?? 0) * left + (matrix[4] ?? 0) * top + (matrix[12] ?? 0)) / weight,
        top:
            origin.top +
            ((matrix[1] ?? 0) * left + (matrix[5] ?? 0) * top + (matrix[13] ?? 0)) / weight,
    };
}

function boundsOf(points: readonly ScreenPoint[]): {
    left: number;
    top: number;
    width: number;
    height: number;
} {
    const lefts = points.map(({ left }) => left);
    const tops = points.map(({ top }) => top);
    return {
        height: Math.max(...tops) - Math.min(...tops),
        left: Math.min(...lefts),
        top: Math.min(...tops),
        width: Math.max(...lefts) - Math.min(...lefts),
    };
}

describe("tile quads on a tilted piece", () => {
    const { height, matrix, width } = topStrip();
    const origin = { left: 200, top: 30 };
    const frame = { matrix, origin };
    function corners(left: number): ScreenPoint[] {
        return rectQuad({ height: 40, left, top: 5, width: 30 }).map((corner) =>
            shown(frame, corner),
        );
    }

    it("finds a piece's inner corner from its shown bounding box, past a transparent border", () => {
        for (const border of [0, 2]) {
            const box = {
                height: height + 2 * border,
                left: -border,
                top: -border,
                width: width + 2 * border,
            };
            const bounds = boundsOf(rectQuad(box).map((corner) => shown(frame, corner)));

            const found = pieceOrigin(matrix, box, bounds);

            expect(found.left).toBeCloseTo(origin.left, 6);
            expect(found.top).toBeCloseTo(origin.top, 6);
        }
    });

    it("recovers a tilted tile's tapered corners from its bounding box", () => {
        const truth = corners(12);

        const quad = tiltedQuad(frame, boundsOf(truth));

        expect(quad).not.toBeNull();
        for (const [index, corner] of truth.entries()) {
            expect(quad?.[index]?.left).toBeCloseTo(corner.left, 6);
            expect(quad?.[index]?.top).toBeCloseTo(corner.top, 6);
        }
        expect((truth[1]?.left ?? 0) - (truth[0]?.left ?? 0)).toBeLessThan(
            (truth[2]?.left ?? 0) - (truth[3]?.left ?? 0),
        );
    });

    it("warps an image of the tile's bounding box onto its shown corners", () => {
        const truth = corners(12);
        const box = boundsOf(truth);
        const warp = quadWarp(box, tiltedQuad(frame, box) ?? rectQuad(box));
        const centred = rectQuad({
            height: box.height,
            left: -box.width / 2,
            top: -box.height / 2,
            width: box.width,
        });

        for (const [index, corner] of centred.entries()) {
            const point = warpPoint(warp, corner);
            expect(point.left + box.left + box.width / 2).toBeCloseTo(truth[index]?.left ?? 0, 6);
            expect(point.top + box.top + box.height / 2).toBeCloseTo(truth[index]?.top ?? 0, 6);
        }
    });

    it("takes a neighbouring slot's shown offset back to the laid step, across and down alike", () => {
        const here = boundsOf(corners(12));
        const warp = quadWarp(here, tiltedQuad(frame, here) ?? rectQuad(here));
        const next = shown(frame, { left: 12 + 15 + 31, top: 5 + 20 + 10 });
        const centre = { left: here.left + here.width / 2, top: here.top + here.height / 2 };

        const laid = unwarpPoint(warp, {
            left: next.left - centre.left,
            top: next.top - centre.top,
        });

        expect(laid.left / (here.width / 30)).toBeCloseTo(31, 1);
        expect(laid.top / (here.height / 40)).toBeCloseTo(10, 1);
    });

    it("leaves a flat tile's image unwarped", () => {
        const box = { height: 40, left: 10, top: 20, width: 30 };

        const warp = quadWarp(box, rectQuad(box));

        expect(warpPoint(warp, { left: 7, top: -3 })).toEqual({
            left: 7,
            top: -3,
        });
    });
});
