import { describe, expect, it } from "vitest";

import {
    FULL_HAND,
    LATEST_DISCARD_GAP,
    RIGHT_LATEST_DISCARD_GAP,
} from "@/entities/table/lib/board-constants";
import {
    type BoardBox,
    type BoardEdges,
    type BoardGeometry,
    type BoardSlots,
    boardGeometry,
} from "@/entities/table/lib/board-geometry";

/** The sizes pinned, in the order each case lists them. */
const SIZES = ["rw", "ow", "core", "c", "w", "core-top"] as const;
const SHORT_DESKTOP_SIZES = ["rw", "w", "core-top"] as const;
const UPRIGHT_SIZES = ["rw", "core", "core-top"] as const;
const PHONE_SIZES = ["rw", "ow"] as const;

const NO_INSETS: BoardEdges = { bottom: 0, left: 0, right: 0, top: 0 };
const LIVE_SLOTS: BoardSlots = { band: "play", corner: true };

/** A window's board under the gutter its page applies: each edge pads the larger of its safe inset and the gutter. */
function windowGeometry(
    { height, width }: BoardBox,
    applied = 0,
    insets: BoardEdges = NO_INSETS,
): BoardGeometry {
    function pad(inset: number): number {
        return Math.max(inset, applied);
    }
    const box = {
        height: height - pad(insets.top) - pad(insets.bottom),
        width: width - pad(insets.left) - pad(insets.right),
    };
    return boardGeometry({ box, gutter: applied, safeInsets: insets, slots: LIVE_SLOTS });
}

describe("boardGeometry", () => {
    it.each([
        { chrome: "regular", family: "desktop", height: 900, width: 1440 },
        { chrome: "large", family: "desktop", height: 1440, width: 2560 },
        { chrome: "small", family: "desktop", height: 600, width: 800 },
        { chrome: "small", family: "desktop", height: 540, width: 1024 },
        { chrome: "small", family: "desktop", height: 900, width: 1100 },
        { chrome: "regular", family: "desktop", height: 900, width: 1120 },
        { chrome: "regular", family: "short-desktop", height: 657, width: 1366 },
        { chrome: "regular", family: "short-desktop", height: 540, width: 1280 },
        { chrome: "regular", family: "short-desktop", height: 770, width: 1440 },
        { chrome: "small", family: "upright", height: 548, width: 375 },
    ])(
        "gives a $width x $height window a $family board with $chrome chrome in a 10px gutter, whichever is applied",
        ({ chrome, family, height, width }) => {
            for (const applied of [0, 10]) {
                const geometry = windowGeometry({ height, width }, applied);
                const { box, lengths } = geometry;
                function length(name: string): number {
                    return lengths[name] ?? Number.NaN;
                }

                expect(geometry).toMatchObject({
                    box: { height: height - 20, width: width - 20 },
                    chrome,
                    family,
                    gutter: 10,
                });
                expect(length("core")).toBeGreaterThan(0);
                expect(FULL_HAND * length("ow")).toBeLessThanOrEqual(
                    box.width - 2 * length("m") - length("own-inline"),
                );
                const [aboveBand, bandTop] =
                    family === "short-desktop"
                        ? [length("cy") + length("h"), length("band-bottom") - length("control-h")]
                        : [
                              length("core-top") + length("core"),
                              length("hand-top") - length("band-reserve"),
                          ];
                expect(aboveBand).toBeLessThanOrEqual(bandTop + 0.001);
            }
        },
    );

    it.each([
        { height: 375, insets: NO_INSETS, width: 667 },
        { height: 539, insets: NO_INSETS, width: 1024 },
        { height: 539, insets: NO_INSETS, width: 1280 },
        { height: 390, insets: { bottom: 21, left: 47, right: 47, top: 0 }, width: 844 },
    ])(
        "gives a $width x $height window a phone board with small chrome and no gutter, whichever is applied",
        ({ height, insets, width }) => {
            for (const applied of [0, 10]) {
                expect(windowGeometry({ height, width }, applied, insets)).toMatchObject({
                    box: {
                        height: height - insets.top - insets.bottom,
                        width: width - insets.left - insets.right,
                    },
                    chrome: "small",
                    family: "phone",
                    gutter: 0,
                });
            }
        },
    );

    it.each([
        [1440, 900, [42, 56, 549.2, 188, 263.2, 114]],
        [1440, 800, [36, 48, 471.6, 162, 226.8, 106]],
        [2560, 1440, [73, 97, 937.2, 309.4, 433.16, 191.603]],
        [800, 600, [22, 29, 295.867, 106.667, 149.334, 87.3327]],
    ])("sizes a %ix%i window's desktop board as its stylesheet did", (width, height, expected) => {
        const { lengths } = windowGeometry({ height, width });

        for (const [index, name] of SIZES.entries()) {
            expect(lengths[name], name).toBeCloseTo(expected[index] ?? Number.NaN, 2);
        }
    });

    it.each([
        [1366, 657, [30, 227.388, 101.623]],
        [1280, 720, [35, 225.4, 109.833]],
        [1440, 770, [38, 235.48, 119.5]],
        [1170, 620, [28, 211.333, 96.0002]],
    ])(
        "sizes a %ix%i window's short desktop board as its stylesheet did",
        (width, height, expected) => {
            const { lengths } = windowGeometry({ height, width });

            for (const [index, name] of SHORT_DESKTOP_SIZES.entries()) {
                expect(lengths[name], name).toBeCloseTo(expected[index] ?? Number.NaN, 2);
            }
        },
    );

    it.each([
        [375, 548, [11, 205.666, 103.934]],
        [800, 801, [30, 393.8, 122]],
    ])("sizes a %ix%i window's upright board as its stylesheet did", (width, height, expected) => {
        const { lengths } = windowGeometry({ height, width });

        for (const [index, name] of UPRIGHT_SIZES.entries()) {
            expect(lengths[name], name).toBeCloseTo(expected[index] ?? Number.NaN, 2);
        }
    });

    it.each([
        [667, 375, [17, 36]],
        [750, 369, [17, 36]],
        [932, 430, [23, 39]],
    ])(
        "sizes a %ix%i window's phone board's river and own tiles jointly, the top river's gap inside its core",
        (width, height, expected) => {
            const { lengths } = windowGeometry({ height, width });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }

            for (const [index, name] of PHONE_SIZES.entries()) {
                expect(length(name), name).toBeCloseTo(expected[index] ?? Number.NaN, 2);
            }
            expect(
                length("reach-top-row3") - length("rh") - LATEST_DISCARD_GAP,
            ).toBeGreaterThanOrEqual(length("core-top") - 0.001);
        },
    );

    it.each([
        [667, 375],
        [1440, 900],
        [390, 844],
    ])(
        "counts the latest discard's gap in a %ix%i window's river reaches, none at the top river's near edge",
        (width, height) => {
            const { lengths } = windowGeometry({ height, width });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const across = length("g") + 4 * length("rh") + LATEST_DISCARD_GAP;
            const runOn = 11 * length("rw") + length("rh") + LATEST_DISCARD_GAP;
            const left = length("cx") - length("hx");
            const right = length("cx") + length("hx");
            const expected = {
                "reach-bottom-right": left + runOn,
                "reach-left": left - across,
                "reach-right": right + across,
                "reach-top-left": right - runOn,
                "reach-top-row3": length("cy") - length("h") - length("g") - 2 * length("rh"),
            };

            for (const [name, reach] of Object.entries(expected)) {
                expect(length(name), name).toBeCloseTo(reach, 3);
            }
            expect(
                length("cy") +
                    length("h") -
                    5 * length("rw") -
                    length("rh") -
                    RIGHT_LATEST_DISCARD_GAP,
            ).toBeGreaterThanOrEqual(length("core-top"));
        },
    );

    it("keeps a narrow upright board's centre at least 100px across", () => {
        expect(windowGeometry({ height: 620, width: 260 }).lengths["c"]).toBeGreaterThanOrEqual(
            100,
        );
    });

    it("keeps the same free box with and without a notice", () => {
        const { lengths } = windowGeometry({ height: 900, width: 1440 });

        expect(lengths["overlay-left"]).toBeGreaterThanOrEqual(lengths["reach-left"] ?? Infinity);
    });

    it("gives an empty box no sizes", () => {
        expect(windowGeometry({ height: 0, width: 0 }).lengths).toEqual({});
    });
});
