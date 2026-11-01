import { describe, expect, it } from "vitest";

import { boardGeometry } from "@/entities/table/lib/board-geometry";

/** The sizes pinned, in the order each case lists them. */
const SIZES = ["rw", "ow", "core", "c", "w", "core-top"] as const;
const SHORT_DESKTOP_SIZES = ["rw", "w", "core-top"] as const;

describe("boardGeometry", () => {
    it.each([
        { chrome: "regular", family: "desktop", height: 880, width: 1420 },
        { chrome: "large", family: "desktop", height: 1420, width: 2540 },
        { chrome: "small", family: "desktop", height: 580, width: 780 },
        { chrome: "regular", family: "short-desktop", height: 637, width: 1346 },
        { chrome: "small", family: "phone", height: 375, width: 667 },
        { chrome: "small", family: "upright", height: 528, width: 355 },
    ])(
        "classes a $width x $height board as a $family board with $chrome chrome",
        ({ chrome, family, ...box }) => {
            expect(boardGeometry(box)).toMatchObject({ chrome, family });
        },
    );

    it.each([
        [1420, 880, [42, 56, 549.2, 188, 263.2, 114]],
        [1420, 780, [36, 48, 471.6, 162, 226.8, 106]],
        [2540, 1420, [73, 97, 937.2, 309.4, 433.16, 191.603]],
        [780, 580, [22, 29, 295.867, 106.667, 149.334, 87.3327]],
    ])("sizes a %ix%i desktop board as its stylesheet did", (width, height, expected) => {
        const { lengths } = boardGeometry({ height, width });

        for (const [index, name] of SIZES.entries()) {
            expect(lengths[name], name).toBeCloseTo(expected[index] ?? Number.NaN, 2);
        }
    });

    it.each([
        [1346, 637, [30, 227.388, 101.623]],
        [1260, 700, [35, 225.4, 109.833]],
        [1420, 750, [38, 235.48, 119.5]],
    ])("sizes a %ix%i short desktop board as its stylesheet did", (width, height, expected) => {
        const { lengths } = boardGeometry({ height, width });

        for (const [index, name] of SHORT_DESKTOP_SIZES.entries()) {
            expect(lengths[name], name).toBeCloseTo(expected[index] ?? Number.NaN, 2);
        }
    });

    it("gives an empty box no sizes", () => {
        expect(boardGeometry({ height: 0, width: 0 }).lengths).toEqual({});
    });
});
