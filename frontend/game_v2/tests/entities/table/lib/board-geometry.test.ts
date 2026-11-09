import { describe, expect, it } from "vitest";

import {
    BAND_ROW_EXTRA,
    DESKTOP_CHROME,
    FACE_FLOOR,
    FULL_HAND,
    LATEST_DISCARD_GAP,
    SIDEWAYS_UNITS,
    TILE_EDGE_SHARE,
    UPRIGHT_DEPTH,
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
import { stripLayout } from "@/entities/table/lib/strip-layout";
import { RIVER_ROW_SIZE } from "@/entities/tile";

/** The sizes pinned, in the order each case lists them. */
const SIZES = ["rw", "ow", "c", "w", "core-top"] as const;
const SHORT_DESKTOP_SIZES = ["rw", "w", "core-top"] as const;
const UPRIGHT_SIZES = ["rw", "c", "core-top"] as const;

const NO_INSETS: BoardEdges = { bottom: 0, left: 0, right: 0, top: 0 };
const LIVE_SLOTS: BoardSlots = { band: "play" };
const REPLAY_SLOTS: BoardSlots = { band: "replay" };

/**
 * A window's board under the padding its page holds: with a gutter applied each edge pads the larger of its safe inset
 * and the gutter, without one (a phone's board) the side and top insets alone and the bottom nothing.
 */
function windowGeometry(
    { height, width }: BoardBox,
    applied = 0,
    insets: BoardEdges = NO_INSETS,
): BoardGeometry {
    function pad(inset: number): number {
        return Math.max(inset, applied);
    }
    const appliedEdges: BoardEdges = {
        bottom: applied === 0 ? 0 : pad(insets.bottom),
        left: pad(insets.left),
        right: pad(insets.right),
        top: pad(insets.top),
    };
    const box = {
        height: height - appliedEdges.top - appliedEdges.bottom,
        width: width - appliedEdges.left - appliedEdges.right,
    };
    return boardGeometry({ appliedEdges, box, safeInsets: insets, slots: LIVE_SLOTS });
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
    ])("fits a full six-tile row along every centre edge at $width x $height", (box) => {
        const { lengths } = windowGeometry(box);
        expect(lengths["c"]).toBeGreaterThanOrEqual(RIVER_ROW_SIZE * (lengths["rw"] ?? Number.NaN));
        expect(lengths["w"]).toBe(lengths["c"]);
    });

    it.each([
        { height: 390, width: 844 },
        { height: 430, width: 932 },
    ])(
        "keeps a $width x $height phone's centre six river tiles and 100px wide, and 68px tall, at least",
        (box) => {
            const { lengths } = windowGeometry(box);
            expect(lengths["w"]).toBeGreaterThanOrEqual(
                Math.max(RIVER_ROW_SIZE * (lengths["rw"] ?? Number.NaN), 100),
            );
            expect(lengths["c"]).toBeGreaterThanOrEqual(68);
        },
    );
});

describe("boardGeometry chrome", () => {
    it.each([
        { badgeH: 54, height: 770, text: 17, width: 1440 },
        { badgeH: 54 + 18 * (3 / 11), height: 900, text: 17 + 7 * (3 / 11), width: 1440 },
        { badgeH: 63, height: 1000, text: 20.5, width: 1727 },
        { badgeH: 72, height: 1440, text: 24, width: 2560 },
    ])(
        "scales a $width x $height window's chrome from the regular record to the large one with its padded box, the top badge's lane an ordinary name wide",
        ({ badgeH, height, text, width }) => {
            const { lengths } = windowGeometry({ height, width }, 10);

            expect(lengths["badge-h"]).toBeCloseTo(badgeH, 6);
            expect(lengths["text"]).toBeCloseTo(text, 6);
            expect(lengths["top-lane"]).toBeGreaterThanOrEqual(8 * text - 0.001);
        },
    );
});

describe("boardGeometry in a phone's browser", () => {
    it.each([LIVE_SLOTS, REPLAY_SLOTS])(
        "lets only a replay's moves meet the bottom river where they leave a phone box no solve, never where the box has one ($band)",
        (slots) => {
            function tiles(width: number, height: number): Record<"ow" | "rw", number | undefined> {
                const { lengths } = boardGeometry({
                    appliedEdges: NO_INSETS,
                    box: { height, width },
                    safeInsets: NO_INSETS,
                    slots,
                });
                return { ow: lengths["ow"], rw: lengths["rw"] };
            }

            expect(tiles(592, 360)).toEqual({ ow: 36, rw: 13 });
            expect(tiles(620, 360)).toEqual({ ow: 36, rw: 13 });
        },
    );

    it.each([
        {
            browser: "iOS 26 Safari, its bars collapsed",
            height: 375,
            insets: NO_INSETS,
            width: 667,
        },
        { browser: "Android Chrome, its bars shown", height: 331, insets: NO_INSETS, width: 891 },
        {
            browser: "Android Chrome, its bars collapsed",
            height: 387,
            insets: NO_INSETS,
            width: 891,
        },
    ])(
        "keeps a $width x $height phone box ($browser) a phone board whose river tile is at least the face floor over an own tile at its floor",
        ({ height, insets, width }) => {
            const { family, lengths } = windowGeometry({ height, width }, 0, insets);

            expect(family).toBe("phone");
            expect(lengths["rw"]).toBeGreaterThanOrEqual(FACE_FLOOR);
            expect(lengths["ow"]).toBeGreaterThanOrEqual(36);
            expect(lengths["oh"]).toBeGreaterThanOrEqual(48);
        },
    );

    it.each([
        {
            board: { height: 414, width: 808 },
            height: 414,
            insets: { bottom: 21, left: 44, right: 44, top: 0 },
            ow: 44,
            rw: 23,
            width: 896,
        },
        {
            board: { height: 390, width: 750 },
            height: 390,
            insets: { bottom: 21, left: 47, right: 47, top: 0 },
            ow: 44,
            rw: 20,
            width: 844,
        },
    ])(
        "runs a full-screen $width x $height phone's board down to the screen's bottom edge, past its bottom inset, at its river and own tiles",
        ({ board, height, insets, ow, rw, width }) => {
            const { box, family, lengths } = windowGeometry({ height, width }, 0, insets);

            expect({ box, family }).toEqual({ box: board, family: "phone" });
            expect(lengths).toMatchObject({ ow, rw });
        },
    );

    it.each([
        {
            browser: "an iPhone 11 in iOS 26 Safari",
            height: 275,
            insets: { bottom: 0, left: 44, right: 44, top: 0 },
            ow: 32,
            rw: 13,
            width: 896,
        },
        {
            browser: "a Galaxy A25 in Android Chrome",
            height: 331,
            insets: NO_INSETS,
            ow: 36,
            rw: 18,
            width: 891,
        },
        {
            browser: "an iPhone SE in iOS 26 Safari",
            height: 236,
            insets: NO_INSETS,
            ow: 32,
            rw: 7,
            width: 667,
        },
        {
            browser: "an iPhone 13 in iOS 26 Safari",
            height: 251,
            insets: { bottom: 0, left: 47, right: 47, top: 0 },
            ow: 32,
            rw: 9,
            width: 844,
        },
    ])(
        "lays a $width x $height box ($browser, its bars shown) out as a phone board at the largest river tile its height holds, the own tile down to the tap floor where that lifts it, and reserves the side strips only the kans the box holds",
        ({ height, insets, ow, rw, width }) => {
            const { family, lengths } = windowGeometry({ height, width }, 0, insets);

            expect(family).toBe("phone");
            expect(lengths).toMatchObject({ ow, rw });
            expect(lengths["side-reach"]).toBeLessThanOrEqual(
                (lengths["hand-top"] ?? 0) - 4 - (lengths["m"] ?? 0),
            );
            expect(lengths["c"]).toBeGreaterThanOrEqual(68);
        },
    );
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
        { height: 530, insets: { bottom: 21, left: 44, right: 44, top: 0 }, width: 896 },
    ])(
        "gives a $width x $height window a phone board with small chrome, no gutter and a bare bottom edge, whichever padding the page holds",
        ({ height, insets, width }) => {
            for (const applied of [0, 10]) {
                expect(windowGeometry({ height, width }, applied, insets)).toMatchObject({
                    box: {
                        height: height - insets.top,
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
        [1440, 900, [39, 62, 234, 234, 94.4]],
        [1440, 800, [34, 54, 204, 204, 82.4]],
        [2560, 1440, [68, 108, 408, 408, 134.8]],
        [800, 600, [21, 33, 126, 126, 71.6]],
        [1727, 1000, [44, 70, 264, 264, 108.4]],
        [1920, 1080, [49, 78, 294, 294, 102.4]],
        [2150, 1700, [80, 106, 480, 480, 188]],
        [2170, 1700, [80, 107, 480, 480, 188]],
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
        [1366, 657, [29, 174, 80.167]],
        [1280, 720, [33, 198, 81.333]],
        [1440, 770, [36, 216, 82]],
        [1170, 620, [27, 162, 77.333]],
    ])(
        "sizes a %ix%i window's short desktop board, a replay's full left river ending over its moves",
        (width, height, expected) => {
            const { lengths } = windowGeometry({ height, width });
            const replay = boardGeometry({
                appliedEdges: NO_INSETS,
                box: { height, width },
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
        [800, 801, [26, 167.27, 114]],
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
        {
            height: 375,
            holdsOffers: true,
            pinned: { "band-shift": 28.667, ow: 39, rw: 17 },
            width: 667,
        },
        { height: 390, holdsOffers: true, pinned: { ow: 39, rw: 17 }, width: 667 },
        { height: 354, holdsOffers: false, pinned: { ow: 36, rw: 19 }, width: 724 },
        { height: 360, holdsOffers: false, pinned: { ow: 36, rw: 19 }, width: 800 },
        { height: 390, holdsOffers: true, pinned: { ow: 44, rw: 20 }, width: 750 },
        { height: 379, holdsOffers: true, pinned: { ow: 37, rw: 21 }, width: 761 },
        { height: 414, holdsOffers: true, pinned: { ow: 44, rw: 23 }, width: 808 },
        { height: 480, holdsOffers: true, pinned: { ow: 50, rw: 24 }, width: 850 },
        {
            height: 430,
            holdsOffers: true,
            pinned: { "band-shift": 38, ow: 45, rw: 24 },
            width: 932,
        },
        {
            height: 500,
            holdsOffers: true,
            pinned: { "control-h": 46.667, ow: 53, rw: 28 },
            width: 1024,
        },
    ])(
        "sizes a $width x $height window's phone board's tiles jointly: a full hand clear of the side strips, the offers' stack in its corner ($holdsOffers), a full left river above the switches' row or past its end, the moves' row short of the bottom river, the furiten mark short of the left river and the top badge's one-line pill above the right river",
        ({ height, holdsOffers, pinned, width }) => {
            const { lengths, tracks } = windowGeometry({ height, width });
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
            expect(length("w")).toBeGreaterThanOrEqual(
                Math.max(RIVER_ROW_SIZE * length("rw"), 100),
            );
            expect(length("c")).toBeGreaterThanOrEqual(68);
            expect({
                furitenShortOfLeftRiver: length("furiten-x") + 88 <= length("reach-left") + 0.001,
                handClearOfStrips:
                    (width - FULL_HAND * length("ow")) / 2 >=
                    length("m") + length("strip-depth") + 6,
                leftRiverClearOfSwitches:
                    leftRiverEnd + 4 <= length("switches-bottom") - length("control-h") + 0.001 ||
                    length("switches-left") + 5 * length("control-h") + 4 * 4 + 8 <=
                        length("reach-left") + 0.001,
                movesShortOfBottomRiver:
                    length("switches-left") + 5 * length("control-h") + 4 * 4 + 8 <=
                    length("cx") - length("hx") + 0.001,
                offersInCorner:
                    (slotAreas(tracks)["actions"]?.[3] ?? 0) -
                        (slotAreas(tracks)["actions"]?.[1] ?? 0) >=
                    44 + 2 * 40 + length("control-h") + 3 * 6,
                topBadgeAboveRightRiver:
                    length("top-badge-top") + length("top-pill-h") + 4 <=
                    length("cy") +
                        length("h") -
                        5 * length("rw") -
                        length("rh") -
                        length("latest-drop-gap") +
                        0.001,
            }).toEqual({
                furitenShortOfLeftRiver: true,
                handClearOfStrips: true,
                leftRiverClearOfSwitches: true,
                movesShortOfBottomRiver: true,
                offersInCorner: holdsOffers,
                topBadgeAboveRightRiver: true,
            });
            expect(
                length("reach-top-row3") - length("rh") - length("latest-drop-gap"),
            ).toBeGreaterThanOrEqual(length("core-top") - 0.001);
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
                appliedEdges: NO_INSETS,
                box: { height, width },
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

    it.each([
        { height: 275, width: 808 },
        { height: 251, width: 750 },
        { height: 236, width: 667 },
    ])(
        "keeps a right seat's three pons on a $width x $height phone board with its browser's bars shown",
        (box) => {
            const { strips, tracks } = windowGeometry(box);
            const origin = slotAreas(tracks)["strip-right"]?.[3] ?? Number.NaN;
            const pon = { depth: UPRIGHT_DEPTH, units: 2 + SIDEWAYS_UNITS };
            const content = { drawn: true, hand: 5, melds: [pon, pon, pon] };
            if (strips === null) {
                throw new Error("The board has no strip rooms");
            }

            const oldest = stripLayout("right", content, strips).melds.at(-1);

            expect(oldest).toBeDefined();
            expect(
                origin - (oldest?.along ?? Number.NaN) - pon.units * (oldest?.tile ?? Number.NaN),
            ).toBeGreaterThanOrEqual(0);
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
        { height: 236, under: false, width: 667 },
        { height: 275, under: false, width: 896 },
        { height: 331, under: false, width: 896 },
        { height: 375, under: true, width: 667 },
        { height: 414, under: true, width: 896 },
    ])(
        "keeps a $width x $height phone's switches' column on the left edge, the left badge clear of it (under: $under)",
        ({ height, under, width }) => {
            const { lengths } = windowGeometry({ height, width });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const columnTop = length("switches-bottom") - 4 * length("switch-h");

            expect(length("switches-right") - length("switches-left")).toBeCloseTo(
                length("switch-h"),
                3,
            );
            expect(columnTop).toBeGreaterThanOrEqual(0);
            expect(columnTop >= length("side-badge-top") + length("badge-h")).toBe(under);
            expect(length("left-badge-x") >= length("switches-right")).toBe(!under);
            expect(length("left-badge-x") + length("left-badge-w")).toBeLessThanOrEqual(
                length("reach-left"),
            );
        },
    );

    it.each([
        { height: 900, labelled: true, width: 1440 },
        { height: 720, labelled: true, width: 1280 },
        { height: 768, labelled: false, width: 1024 },
    ])(
        "reserves a $width x $height board's switches their whole names' row ($labelled), short of the decisions",
        ({ height, labelled, width }) => {
            const { lengths } = windowGeometry({ height, width });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const gap = length("chip-gap");
            const row = labelled
                ? 3 * length("switch-label-w") + 2 * gap
                : 4 * length("switch-h") + 3 * gap;

            expect(length("switches-right") - length("switches-left")).toBeCloseTo(row, 3);
            expect(length("switches-right") + length("band-gap")).toBeLessThanOrEqual(
                length("actions-left"),
            );
        },
    );

    it.each([
        { height: 770, stacked: true, width: 1440 },
        { height: 640, stacked: false, width: 1127 },
    ])(
        "steps a $width x $height short desktop's switches past a stacked meld ($stacked), moves clear of the river",
        ({ height, stacked, width }) => {
            const { lengths } = boardGeometry({
                appliedEdges: { bottom: 10, left: 10, right: 10, top: 10 },
                box: { height: height - 20, width: width - 20 },
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
    it("sizes a 1440x770 short desktop board's side badges to their lanes, past a 200px card", () => {
        const { family, lengths } = windowGeometry({ height: 770, width: 1440 });

        expect(family).toBe("short-desktop");
        expect(lengths["left-badge-w"]).toBeGreaterThan(300);
        expect(lengths["right-badge-w"]).toBeGreaterThan(300);
    });

    it("keeps a 932x430 phone board's side badges to their 130px card at most", () => {
        const { family, lengths } = windowGeometry({ height: 430, width: 932 });

        expect(family).toBe("phone");
        expect(lengths["left-badge-w"]).toBeLessThanOrEqual(130);
        expect(lengths["right-badge-w"]).toBeLessThanOrEqual(130);
    });

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
            actions: [403.2, 126, 663, 309.9],
            corner: [0, 4, 583, 375],
            field: [90, 126, 171.8, 287.9],
            "field-beside": [554.3, 265.9, 634.3, 313.9],
            hand: [48.8, 317.9, 663, 369.9],
            "strip-left": [4, 44, 76, 261.9],
            "strip-right": [591, 4, 663, 297.3],
            "strip-top": [4, 4, 524.5, 38],
            switches: [44, 0, 667, 313.9],
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
        { height: 844, lane: 124.1, oneRow: false, width: 390 },
        { height: 1024, lane: 251.9, oneRow: true, width: 768 },
    ])(
        "stands a $width x $height upright replay's group in the own badge's row only where it leaves the badge an ordinary lane ($oneRow)",
        ({ height, lane, oneRow, width }) => {
            const { lengths } = boardGeometry({
                appliedEdges: NO_INSETS,
                box: { height, width },
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
