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
    type BoardTracks,
    boardGeometry,
} from "@/entities/table/lib/board-geometry";

/** The sizes pinned, in the order each case lists them. */
const SIZES = ["rw", "ow", "core", "c", "w", "core-top"] as const;
const SHORT_DESKTOP_SIZES = ["rw", "w", "core-top"] as const;
const UPRIGHT_SIZES = ["rw", "core", "core-top"] as const;

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

/** Each named line of a grid template at its offset from the grid's start (px). */
function trackLines(template: string): Map<string, number> {
    const lines = new Map<string, number>();
    let offset = 0;
    for (const { groups } of template.matchAll(/\[(?<names>[^\]]*)\]|(?<size>[\d.e+-]+)px/gu)) {
        for (const name of groups?.names?.split(" ") ?? []) {
            lines.set(name, offset);
        }
        offset += Number(groups?.size ?? 0);
    }
    return lines;
}

/** Each slot's area on the shell's tracks: its start and end lines across, then down, to a tenth of a pixel. */
function slotAreas({ columns, rows }: BoardTracks): Record<string, number[]> {
    const across = trackLines(columns);
    const down = trackLines(rows);
    const slots = [...across.keys()]
        .filter((name) => name.endsWith("-start"))
        .map((name) => name.slice(0, -6));
    return Object.fromEntries(
        slots.map((slot) => [
            slot,
            [
                across.get(`${slot}-start`),
                down.get(`${slot}-start`),
                across.get(`${slot}-end`),
                down.get(`${slot}-end`),
            ].map((line) => Math.round((line ?? Number.NaN) * 10) / 10),
        ]),
    );
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
        [1440, 900, [42, 56, 549.2, 173.2, 242.48, 114]],
        [1440, 800, [36, 48, 471.6, 147.6, 206.64, 106]],
        [2560, 1440, [73, 97, 937.2, 295.2, 413.28, 191.6]],
        [800, 600, [22, 29, 295.867, 91.867, 128.613, 87.333]],
    ])(
        "sizes a %ix%i window's desktop board, its core holding the latest discards' gaps",
        (width, height, expected) => {
            const { lengths } = windowGeometry({ height, width });

            for (const [index, name] of SIZES.entries()) {
                expect(lengths[name], name).toBeCloseTo(expected[index] ?? Number.NaN, 2);
            }
        },
    );

    it.each([
        [1366, 657, [30, 207.788, 101.623]],
        [1280, 720, [35, 204.4, 109.833]],
        [1440, 770, [38, 217, 119.5]],
        [1170, 620, [28, 198.8, 96]],
    ])(
        "sizes a %ix%i window's short desktop board, its core holding the latest discards' gaps",
        (width, height, expected) => {
            const { lengths } = windowGeometry({ height, width });

            for (const [index, name] of SHORT_DESKTOP_SIZES.entries()) {
                expect(lengths[name], name).toBeCloseTo(expected[index] ?? Number.NaN, 2);
            }
        },
    );

    it.each([
        [375, 548, [11, 205.666, 96.933]],
        [800, 801, [30, 386.8, 122]],
    ])(
        "sizes a %ix%i window's upright board, its core holding the latest discards' gaps",
        (width, height, expected) => {
            const { lengths } = windowGeometry({ height, width });

            for (const [index, name] of UPRIGHT_SIZES.entries()) {
                expect(lengths[name], name).toBeCloseTo(expected[index] ?? Number.NaN, 2);
            }
        },
    );

    it.each([
        { above: true, height: 375, pinned: { "band-shift": 0, ow: 36, rw: 17 }, width: 667 },
        { above: true, height: 369, pinned: { ow: 36, rw: 16 }, width: 750 },
        { above: true, height: 480, pinned: { ow: 40, rw: 24 }, width: 850 },
        {
            above: false,
            height: 430,
            pinned: { "band-shift": 36.667, "corner-in": 1, ow: 39, "right-origin": 342, rw: 23 },
            width: 932,
        },
        { above: false, height: 500, pinned: { "control-h": 43.333, ow: 44, rw: 26 }, width: 1024 },
    ])(
        "sizes a $width x $height window's phone board's tiles jointly, a full left river over the switches ending above them ($above)",
        ({ above, height, pinned, width }) => {
            const { lengths } = windowGeometry({ height, width });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const leftRiverEnd =
                length("cy") - length("h") + 5 * length("rw") + length("rh") + LATEST_DISCARD_GAP;

            for (const [name, value] of Object.entries(pinned)) {
                expect(length(name), name).toBeCloseTo(value, 2);
            }
            expect(
                length("reach-top-row3") - length("rh") - LATEST_DISCARD_GAP,
            ).toBeGreaterThanOrEqual(length("core-top") - 0.001);
            expect(leftRiverEnd <= length("switches-bottom") - length("control-h")).toBe(above);
        },
    );

    it.each([
        [667, 375],
        [1440, 900],
        [1366, 657],
        [390, 844],
    ])(
        "counts the latest discard's gap in a %ix%i window's river reaches, the core holding the top river's",
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
                Math.min(
                    length("cy") +
                        length("h") -
                        5 * length("rw") -
                        length("rh") -
                        RIGHT_LATEST_DISCARD_GAP,
                    length("reach-top-row3") - length("rh") - LATEST_DISCARD_GAP,
                ),
            ).toBeGreaterThanOrEqual(length("core-top") - 0.001);
        },
    );

    it("keeps a narrow upright board's centre at least 100px across", () => {
        expect(windowGeometry({ height: 620, width: 260 }).lengths["w"]).toBeGreaterThanOrEqual(
            100,
        );
    });

    it("keeps the notices' field and the cog free of the panel", () => {
        const { lengths } = windowGeometry({ height: 900, width: 1440 });
        const stepped = windowGeometry({ height: 620, width: 1170 }).lengths;
        function length(name: string): number {
            return stepped[name] ?? Number.NaN;
        }

        expect(lengths["overlay-left"]).toBeGreaterThanOrEqual(lengths["reach-left"] ?? Infinity);
        expect(length("corner-shift")).toBeGreaterThan(0);
        expect(length("overlay-right")).toBeGreaterThanOrEqual(
            length("m") + length("corner-shift") + length("menu-size"),
        );
    });

    it("gives an empty box no sizes", () => {
        expect(windowGeometry({ height: 0, width: 0 }).lengths).toEqual({});
    });
});

describe("boardGeometry's shell tracks", () => {
    it("lays a landscape phone's slots where its board measured them", () => {
        expect(slotAreas(windowGeometry({ height: 375, width: 667 }).tracks)).toEqual({
            actions: [499, 124.9, 663, 314.3],
            corner: [0, 4, 634.3, 375],
            field: [82, 102, 166, 228.3],
            "field-beside": [583, 272.3, 663, 318.3],
            hand: [70.7, 322.3, 663, 370.3],
            switches: [44, 0, 667, 276.3],
        });
    });
});
