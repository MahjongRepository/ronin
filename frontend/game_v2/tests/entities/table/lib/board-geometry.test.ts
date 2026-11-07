import { describe, expect, it } from "vitest";

import {
    BAND_ROW_EXTRA,
    DESKTOP_CHROME,
    FULL_HAND,
    LATEST_DISCARD_GAP,
    TILE_EDGE_SHARE,
    UPRIGHT_NOTICE_GAP,
    UPRIGHT_NOTICE_ROOM,
} from "@/entities/table/lib/board-constants";
import {
    type BoardBox,
    type BoardEdges,
    type BoardGeometry,
    type BoardSlots,
    type BoardTracks,
    boardGeometry,
    shellTracks,
} from "@/entities/table/lib/board-geometry";
import { RIVER_ROW_SIZE } from "@/entities/tile";

/** The sizes pinned, in the order each case lists them. */
const SIZES = ["rw", "ow", "c", "w", "core-top"] as const;
const SHORT_DESKTOP_SIZES = ["rw", "w", "core-top"] as const;
const UPRIGHT_SIZES = ["rw", "c", "core-top"] as const;

const NO_INSETS: BoardEdges = { bottom: 0, left: 0, right: 0, top: 0 };
const LIVE_SLOTS: BoardSlots = { band: "play" };
const REPLAY_SLOTS: BoardSlots = { band: "replay" };

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

describe("boardGeometry centre", () => {
    it.each([
        { height: 800, width: 800 },
        { height: 801, width: 800 },
        { height: 1601, width: 1600 },
        { height: 390, width: 844 },
        { height: 430, width: 932 },
    ])("fits a full six-tile row along every centre edge at $width x $height", (box) => {
        const { lengths } = windowGeometry(box);
        expect(lengths["c"]).toBeGreaterThanOrEqual(RIVER_ROW_SIZE * (lengths["rw"] ?? Number.NaN));
        expect(lengths["w"]).toBe(lengths["c"]);
    });
});

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
                expect(length("w")).toBe(length("c"));
                expect(FULL_HAND * length("ow")).toBeLessThanOrEqual(
                    box.width - 2 * length("m") - length("own-inline"),
                );
                const coreBottom =
                    length("cy") +
                    length("h") +
                    length("g") +
                    3 * length("rh") +
                    length("latest-drop-gap");
                const [aboveBand, bandTop] = {
                    desktop: [
                        coreBottom,
                        length("band-bottom") -
                            length("control-h") -
                            length("row-rise") -
                            BAND_ROW_EXTRA,
                    ],
                    "short-desktop": [
                        length("cy") + length("h"),
                        length("band-bottom") - length("control-h"),
                    ],
                    upright: [
                        coreBottom,
                        length("notices-bottom") - UPRIGHT_NOTICE_ROOM - UPRIGHT_NOTICE_GAP,
                    ],
                }[family] ?? [Number.NaN, Number.NaN];
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
        [1440, 900, [38, 50, 228, 228, 94.8]],
        [1440, 800, [33, 44, 198, 198, 80.8]],
        [2560, 1440, [67, 89, 402, 402, 133.2]],
        [800, 600, [21, 28, 126, 126, 59.6]],
    ])(
        "fits six-tile rows along both centre edges in a %ix%i desktop, keeping the latest discards inside the core",
        (width, height, expected) => {
            const { lengths } = windowGeometry({ height, width });
            expect(lengths["c"]).toBeGreaterThanOrEqual(
                RIVER_ROW_SIZE * (lengths["rw"] ?? Number.NaN),
            );
            expect(lengths["w"]).toBe(lengths["c"]);

            for (const [index, name] of SIZES.entries()) {
                expect(lengths[name], name).toBeCloseTo(expected[index] ?? Number.NaN, 2);
            }
        },
    );

    it.each([
        [1366, 657, [29, 174, 77.5]],
        [1280, 720, [33, 198, 78.667]],
        [1440, 770, [35, 210, 87.667]],
        [1170, 620, [27, 162, 74]],
    ])(
        "sizes a %ix%i window's short desktop board, a replay's full left river ending over its moves",
        (width, height, expected) => {
            const { lengths } = windowGeometry({ height, width });
            const replay = boardGeometry({
                box: { height, width },
                gutter: 0,
                safeInsets: NO_INSETS,
                slots: REPLAY_SLOTS,
            }).lengths;
            function length(name: string): number {
                return replay[name] ?? Number.NaN;
            }
            const leftRiverEnd =
                length("cy") -
                length("h") +
                5 * length("rw") +
                length("rh") +
                length("latest-drop-gap");

            for (const [index, name] of SHORT_DESKTOP_SIZES.entries()) {
                expect(lengths[name], name).toBeCloseTo(expected[index] ?? Number.NaN, 2);
            }
            const { movesH, switchH } = DESKTOP_CHROME.regular;
            const switchesTop = length("switches-bottom") - Math.max(movesH, switchH);

            expect(leftRiverEnd + 4).toBeLessThanOrEqual(switchesTop + 0.001);
        },
    );

    it.each([
        [375, 548, [10, 114.333, 93.667]],
        [800, 801, [26, 168.18, 114]],
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
        { above: true, height: 375, pinned: { "band-shift": 28.667, ow: 36, rw: 17 }, width: 667 },
        { above: true, height: 369, pinned: { ow: 36, rw: 16 }, width: 750 },
        { above: true, height: 480, pinned: { ow: 40, rw: 24 }, width: 850 },
        {
            above: true,
            height: 430,
            pinned: { "band-shift": 0, ow: 36, rw: 21 },
            width: 932,
        },
        { above: true, height: 500, pinned: { "control-h": 41.667, ow: 42, rw: 25 }, width: 1024 },
    ])(
        "sizes a $width x $height window's phone board's tiles jointly, a full left river over the switches ending above them ($above), else past the moves' place over the own badge",
        ({ above, height, pinned, width }) => {
            const { lengths } = windowGeometry({ height, width });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const leftRiverEnd =
                length("cy") -
                length("h") +
                5 * length("rw") +
                length("rh") +
                length("latest-drop-gap");

            for (const [name, value] of Object.entries(pinned)) {
                expect(length(name), name).toBeCloseTo(value, 2);
            }
            expect(length("w")).toBe(length("c"));
            expect(
                length("reach-top-row3") - length("rh") - length("latest-drop-gap"),
            ).toBeGreaterThanOrEqual(length("core-top") - 0.001);
            const pastMoves =
                length("reach-left") >=
                    length("switches-left") + 5 * length("control-h") + 4 * 4 - 0.001 &&
                leftRiverEnd <= length("hand-top") - length("own-rise") + 0.001;
            expect(leftRiverEnd <= length("switches-bottom") - length("control-h")).toBe(above);
            expect(above || pastMoves).toBe(true);
        },
    );

    it.each([
        [667, 375],
        [1440, 900],
        [1366, 657],
        [390, 844],
    ])(
        "reserves nineteen discards and the latest gap, deeper by the tile edge along the light off a phone, in a %ix%i window without reserving a twelve-tile third row",
        (width, height) => {
            const { family, lengths } = windowGeometry({ height, width });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const across = length("g") + 4 * length("rh") + LATEST_DISCARD_GAP;
            const runOn = 6 * length("rw") + length("rh") + LATEST_DISCARD_GAP;
            const left = length("cx") - length("hx");
            const right = length("cx") + length("hx");
            const expected = {
                "latest-discard-gap": LATEST_DISCARD_GAP,
                "latest-drop-gap":
                    LATEST_DISCARD_GAP +
                    (family === "phone" ? 0 : Math.round(TILE_EDGE_SHARE * length("rw"))),
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
                        length("latest-drop-gap"),
                    length("reach-top-row3") - length("rh") - length("latest-drop-gap"),
                ),
            ).toBeGreaterThanOrEqual(length("core-top") - 0.001);
        },
    );

    it.each([
        { height: 620, width: 260 },
        { height: 601, width: 600 },
    ])("keeps an upright $width x $height centre square and at least 100px across", (box) => {
        const { lengths } = windowGeometry(box);
        expect(lengths["w"]).toBeGreaterThanOrEqual(100);
        expect(lengths["c"]).toBe(lengths["w"]);
    });

    it("keeps the notices' field free of the panel", () => {
        const { lengths } = windowGeometry({ height: 900, width: 1440 });

        expect(lengths["overlay-left"]).toBeGreaterThanOrEqual(lengths["reach-left"] ?? Infinity);
    });

    it("gives an empty box no sizes", () => {
        expect(windowGeometry({ height: 0, width: 0 }).lengths).toEqual({});
    });
});

describe("boardGeometry's counters", () => {
    it.each([
        { height: 640, slots: REPLAY_SLOTS, width: 360 },
        { height: 620, slots: LIVE_SLOTS, width: 340 },
        { height: 548, slots: LIVE_SLOTS, width: 375 },
    ])(
        "stands a $width x $height upright board's dora box 6px over the left badge, clear of the top badge",
        ({ height, slots, width }) => {
            const { lengths } = boardGeometry({
                box: { height, width },
                gutter: 0,
                safeInsets: NO_INSETS,
                slots,
            });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const doraRight = length("side-badge-x") + length("counters-w");
            const doraBottom = length("counters-top") + length("counters-h");
            const topBadgeBottom = length("top-badge-top") + length("badge-h");
            const topLaneStart = length("top-strip-x") - length("top-lane");

            expect(length("side-badge-top") - doraBottom).toBeCloseTo(6, 3);
            expect(topLaneStart >= doraRight || length("counters-top") >= topBadgeBottom).toBe(
                true,
            );
        },
    );
});

describe("boardGeometry's strips", () => {
    it.each([
        { height: 900, under: 0, width: 1440 },
        { height: 548, under: 2, width: 375 },
    ])(
        "runs a $width x $height board's right strip to the top margin, past $under top strip tiles",
        ({ height, under, width }) => {
            const { lengths, strips, tracks } = windowGeometry({ height, width });
            const origin = slotAreas(tracks)["strip-right"]?.[3] ?? Number.NaN;
            const end =
                (lengths["m"] ?? Number.NaN) + (under > 0 ? under * (lengths["rw"] ?? 0) + 8 : 0);

            expect(strips?.right.line).toBeCloseTo(origin - end, 1);
            expect(strips?.right.deepLine).toBe(strips?.right.line);
        },
    );

    it("runs a desktop's left first line past the switches to the bottom margin for every meld's depth", () => {
        const { box, lengths, strips, tracks } = windowGeometry({ height: 900, width: 1440 });
        function length(name: string): number {
            return lengths[name] ?? Number.NaN;
        }
        const start = slotAreas(tracks)["strip-left"]?.[1] ?? Number.NaN;

        expect(length("switches-left")).toBeGreaterThan(length("m") + 2 * length("rw"));
        expect(start + (strips?.left.line ?? 0)).toBeCloseTo(box.height - length("m"), 1);
        expect(strips?.left.deepLine).toBe(strips?.left.line);
    });

    it.each([
        { height: 770, stacked: true, width: 1440 },
        { height: 640, stacked: false, width: 1127 },
    ])(
        "steps a $width x $height short desktop's switches past a stacked meld ($stacked), moves clear of the river",
        ({ height, stacked, width }) => {
            const { lengths } = boardGeometry({
                box: { height: height - 20, width: width - 20 },
                gutter: 10,
                safeInsets: NO_INSETS,
                slots: REPLAY_SLOTS,
            });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const movesEnd = length("switches-left") + length("moves-w");

            expect(length("switches-left") > length("m") + 2 * length("rw")).toBe(stacked);
            expect(length("cx") - length("hx")).toBeGreaterThanOrEqual(movesEnd + 8 - 0.001);
        },
    );
});

describe("boardGeometry's shell tracks", () => {
    it.each([
        { height: 548, width: 375 },
        { height: 801, width: 800 },
    ])(
        "reserves an upright $width x $height switch row clear of decisions, notices and the hand",
        (box) => {
            const { tracks } = windowGeometry(box);
            const areas = slotAreas(tracks);
            function edge(slot: string, index: number): number {
                return areas[slot]?.[index] ?? Number.NaN;
            }

            expect(edge("switches", 2) - edge("switches", 0)).toBeGreaterThanOrEqual(4 * 40);
            expect(edge("switches", 3) - edge("switches", 1)).toBe(40);
            expect(edge("switches", 2)).toBeLessThan(edge("actions", 0));
            expect(
                Math.max(edge("field", 3), edge("strip-left", 3), edge("strip-right", 3)),
            ).toBeLessThan(edge("switches", 1));
            expect(edge("switches", 3)).toBe(edge("actions", 3));
            expect(edge("switches", 3)).toBeLessThan(edge("hand", 1));
        },
    );

    it.each([
        { height: 800, width: 1280 },
        { height: 375, width: 667 },
    ])("keeps the $width x $height settings target clear of both top corner strips", (box) => {
        const { lengths, tracks } = windowGeometry(box);
        const areas = slotAreas(tracks);
        const cornerRight = areas["corner"]?.[2] ?? Number.NaN;
        const menuSize = lengths["menu-size"] ?? Number.NaN;

        expect(cornerRight).toBeLessThan(areas["strip-right"]?.[0] ?? Number.NaN);
        expect(cornerRight - menuSize).toBeGreaterThan(areas["strip-top"]?.[2] ?? Number.NaN);
    });

    it("lays a landscape phone's slots where its board measured them", () => {
        expect(slotAreas(windowGeometry({ height: 375, width: 667 }).tracks)).toEqual({
            actions: [499, 126, 663, 314.3],
            corner: [0, 4, 583, 375],
            field: [82, 126, 166, 228.3],
            "field-beside": [554.3, 270.3, 634.3, 318.3],
            hand: [70.7, 322.3, 663, 370.3],
            "strip-left": [4, 44, 76, 266.3],
            "strip-right": [591, 4, 663, 297.3],
            "strip-top": [4, 4, 490.3, 38],
            switches: [44, 0, 667, 276.3],
        });
    });

    it("places the settings below the top strip and badge in a near-square landscape window", () => {
        const { lengths, tracks } = windowGeometry({ height: 699, width: 700 });
        const areas = slotAreas(tracks);
        const cornerTop = areas["corner"]?.[1] ?? Number.NaN;

        expect(cornerTop).toBeGreaterThan(areas["strip-top"]?.[3] ?? Number.NaN);
        expect(cornerTop).toBeGreaterThan(
            (lengths["top-badge-top"] ?? Number.NaN) + DESKTOP_CHROME.small.badgeH,
        );
        expect(areas["corner"]?.[2]).toBeLessThan(areas["strip-right"]?.[0] ?? Number.NaN);
    });

    it("ends a narrow desktop's notices' field short of the left river, every slot on lines of its own", () => {
        const { lengths, tracks } = windowGeometry({ height: 900, width: 1100 });
        const areas = Object.values(slotAreas(tracks));

        expect(slotAreas(tracks)["field"]?.[2]).toBeCloseTo((lengths["reach-left"] ?? 0) - 8, 1);
        expect(
            areas.filter(([left, top, right, bottom]) => !(left < right && top < bottom)),
        ).toEqual([]);
    });

    it("keeps an empty or inverted area's end on a line past its start, a 0px track apart", () => {
        const kept = { bottom: 60, left: 40, right: 120, top: 20 };
        const inverted = { bottom: 50, left: 90, right: 70, top: 50 };

        expect(shellTracks({ inverted, kept }, { height: 100, width: 200 })).toEqual({
            columns:
                "40px [kept-start] 50px [inverted-start] 0px [inverted-end] 30px [kept-end] 80px",
            rows: "20px [kept-start] 30px [inverted-start] 0px [inverted-end] 10px [kept-end] 40px",
        });
    });
});

describe("boardGeometry on a replay", () => {
    it.each([
        { height: 844, lane: 102.2, oneRow: false, width: 390 },
        { height: 1024, lane: 200.8, oneRow: true, width: 768 },
    ])(
        "stands a $width x $height upright replay's group in the own badge's row only where it leaves the badge an ordinary lane ($oneRow)",
        ({ height, lane, oneRow, width }) => {
            const { lengths } = boardGeometry({
                box: { height, width },
                gutter: 0,
                safeInsets: NO_INSETS,
                slots: REPLAY_SLOTS,
            });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const handTop = length("hand-top");

            expect(length("actions-bottom")).toBeCloseTo(
                oneRow ? handTop - length("own-meld-rise") - 2 : handTop - length("own-rise") - 4,
                3,
            );
            expect(length("own-lane")).toBeCloseTo(lane, 3);
        },
    );
});
