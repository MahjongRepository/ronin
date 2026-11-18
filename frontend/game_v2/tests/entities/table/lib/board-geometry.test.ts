import { describe, expect, it } from "vitest";

import { cogSquare, riverReserves } from "#tests/fixtures/board-rects";
import {
    FACE_FLOOR,
    FULL_HAND,
    LARGE_CHROME_HEIGHT,
    LARGE_CHROME_WIDTH,
    LATEST_DISCARD_GAP,
    LYING_Y_SHARE,
    PAGE_GUTTER,
    PHONE_FELT_BY_HEIGHT,
    PHONE_HEIGHT,
    PHONE_OWN_FLOOR,
    PHONE_OWN_GIVEN_FOR_RIVER,
    SIDEWAYS_UNITS,
    SIDE_LANE_GAP,
    SMALL_CHROME_WIDTH,
    TILE_EDGE_SHARE,
    TOP_HAND_BACK_EDGE_SHARE,
    UPRIGHT_DEPTH,
} from "@/entities/table/lib/board-constants";
import {
    type BoardBox,
    type BoardEdges,
    type BoardGeometry,
    type BoardInput,
    type BoardRect,
    type BoardSlots,
    type BoardTracks,
    boardGeometry,
    desktopPlanMisfits,
    phonePromptHeight,
    shellTracks,
} from "@/entities/table/lib/board-geometry";
import {
    type StripRooms,
    type StripSeat,
    ownMeldTile,
    stripLayout,
} from "@/entities/table/lib/strip-layout";
import { RIVER_ROW_SIZE, STANDING_BODY, STANDING_OVERHANG } from "@/entities/tile";

/** The sizes pinned, in the order each case lists them. */
const SIZES = ["rw", "ow", "core-top", "col-left"] as const;

const NO_INSETS: BoardEdges = { bottom: 0, left: 0, right: 0, top: 0 };
const WIDEST_PROMPT_IN_ONE_ROW = 450;
const WIDEST_PROMPT_FIRST_OF_TWO_ROWS = 238;
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

function ownRowDepth(lengths: Readonly<Record<string, number>>): number {
    return Math.max(
        STANDING_OVERHANG * (lengths["ow"] ?? 0),
        TILE_EDGE_SHARE * (lengths["own-meld-tile"] ?? 0),
    );
}

/** Whether a desktop's own tile is 1.2 to 1.45 river tiles, floored to a pixel. */
function ownTileByRiver(lengths: Readonly<Record<string, number>>): boolean {
    const [rw = 0, ow = 0] = [lengths["rw"], lengths["ow"]];
    return ow >= 1.2 * rw && ow <= Math.floor(1.45 * rw);
}

/** A desktop's own row's room: the table between its side strips' lanes (px). */
function rowBetweenLanes(lengths: Readonly<Record<string, number>>): number {
    const lane = (lengths["strip-depth"] ?? 0) + SIDE_LANE_GAP;
    return (lengths["col-right"] ?? 0) - (lengths["col-left"] ?? 0) - 2 * lane;
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

/** Each length to a tenth of a pixel, as `slotAreas` rounds an area's lines. */
function tenths(edges: readonly number[]): number[] {
    return edges.map((edge) => Math.round(edge * 10) / 10);
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

describe("boardGeometry chrome", () => {
    it.each([
        { height: 770, pillH: 30, text: 17, width: 1440 },
        { height: 900, pillH: 30 + 12 * (3 / 11), text: 17 + 7 * (3 / 11), width: 1440 },
        { height: 1000, pillH: 36, text: 20.5, width: 1727 },
        { height: 1440, pillH: 42 * (82 / 70), text: 24 * (82 / 70), width: 2560 },
    ])(
        "scales a $width x $height window's chrome from the regular record to the large one with its padded box, and past it with the river tile, one plate pill",
        ({ height, pillH, text, width }) => {
            const { lengths } = windowGeometry({ height, width }, 10);

            expect(lengths["pill-h"]).toBeCloseTo(pillH, 6);
            expect(lengths["text"]).toBeCloseTo(text, 6);
        },
    );
});

describe("boardGeometry in a phone's browser", () => {
    it.each([
        { height: 360, width: 592 },
        { height: 375, width: 667 },
    ])(
        "sizes a $width x $height phone box's tiles and strips alike for a live board and a replay",
        (box) => {
            function placed(slots: BoardSlots): Pick<BoardGeometry, "strips"> & {
                readonly tiles: Record<"ow" | "rw", number | undefined>;
            } {
                const { lengths, strips } = boardGeometry({
                    appliedEdges: NO_INSETS,
                    box,
                    safeInsets: NO_INSETS,
                    slots,
                });
                return { strips, tiles: { ow: lengths["ow"], rw: lengths["rw"] } };
            }

            expect(placed(REPLAY_SLOTS)).toEqual(placed(LIVE_SLOTS));
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
            browser: "a phone narrower than its felt's rails, under the supported width",
            height: 320,
            insets: NO_INSETS,
            width: 568,
        },
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
            ow: 47,
            rw: 23,
            width: 896,
        },
        {
            board: { height: 390, width: 750 },
            height: 390,
            insets: { bottom: 21, left: 47, right: 47, top: 0 },
            ow: 43,
            rw: 22,
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
            ow: 37,
            rw: 13,
            width: 896,
        },
        {
            browser: "a Galaxy A25 in Android Chrome",
            height: 331,
            insets: NO_INSETS,
            ow: 38,
            rw: 18,
            width: 891,
        },
        {
            browser: "an iPhone SE in iOS 26 Safari",
            height: 236,
            insets: NO_INSETS,
            ow: 36,
            rw: 9,
            width: 667,
        },
        {
            browser: "an iPhone 13 in iOS 26 Safari",
            height: 251,
            insets: { bottom: 0, left: 47, right: 47, top: 0 },
            ow: 34,
            rw: 11,
            width: 844,
        },
    ])(
        "lays a $width x $height box ($browser, its bars shown) out as a phone board at the largest river tile its height holds, the own tile down to the tap floor where that lifts it, and reserves the side strips only the kans the box holds",
        ({ height, insets, ow, rw, width }) => {
            const { family, lengths } = windowGeometry({ height, width }, 0, insets);

            expect(family).toBe("phone");
            expect(lengths).toMatchObject({ ow, rw });
            expect(lengths["side-reach"]).toBeLessThanOrEqual(
                (lengths["lines-end"] ?? 0) - (lengths["m"] ?? 0),
            );
            expect(lengths["c"]).toBeGreaterThanOrEqual(68 - 1);
        },
    );

    it.each([{ height: 275, insets: { bottom: 0, left: 44, right: 44, top: 0 }, width: 896 }])(
        "stands a $width x $height box's side lanes beside its own row where above it they would cost the river tile, not hold three kans at the face floor or not leave the decisions' band the widest prompt's rows, both lines and the bars down to the board's foot, its felt holding the column within rails that hold the controls, held as the box grows a pixel taller, the counters crossing its rim",
        ({ height, insets, width }) => {
            const { box, lengths, strips, tracks } = windowGeometry({ height, width }, 0, insets);
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const areas = slotAreas(tracks);
            const foot = box.height - length("m");

            expect({
                leftLaneShortOfRow: areas["strip-left"]?.[2],
                leftLine: strips?.left.line,
                rightLaneShortOfRow: areas["strip-right"]?.[0],
                rightLine: strips?.right.line,
                switchesFoot: areas["switches"]?.[3],
            }).toEqual({
                leftLaneShortOfRow: tenths([length("own-start") - 6])[0],
                leftLine: foot - length("m"),
                rightLaneShortOfRow: tenths([length("own-start") + length("own-row-w") + 6])[0],
                rightLine: foot - length("m"),
                switchesFoot: tenths([foot])[0],
            });
            const shorter = windowGeometry({ height: height - 1, width }, 0, insets).lengths;
            expect({
                countersCrossRim: length("counters-x") + length("counters-w") > length("felt-left"),
                feltHeldAcrossHeight:
                    Math.abs((shorter["felt-left"] ?? 0) - length("felt-left")) <= PAGE_GUTTER,
                feltHoldsColumn:
                    length("felt-left") <= length("col-left") &&
                    length("felt-right") >= length("col-right") &&
                    Math.abs(length("felt-left") + length("felt-right") - box.width) <= 0.1,
                railsHoldControls:
                    length("felt-left") >=
                    length("m") + Math.max(length("replay-w"), length("menu-size")),
            }).toEqual({
                countersCrossRim: true,
                feltHeldAcrossHeight: true,
                feltHoldsColumn: true,
                railsHoldControls: true,
            });
        },
    );
});

/** The replay's board in a live board's box. */
function replayOf({ box }: BoardGeometry): BoardGeometry {
    return boardGeometry({
        appliedEdges: { bottom: 10, left: 10, right: 10, top: 10 },
        box,
        safeInsets: NO_INSETS,
        slots: REPLAY_SLOTS,
    });
}

/**
 * Whether a desktop replay's controls stand in one row along the live decisions' band's foot from its start, clear of
 * the own pill but for a 2px graze, the panel above them.
 */
function replayInRow(live: BoardGeometry, replay: BoardGeometry): boolean {
    const [bandLeft = 0, , bandRight = 0, bandBottom = 0] = slotAreas(live.tracks)["actions"] ?? [];
    const [left = 0, top = 0, right = 0, bottom = 0] = slotAreas(replay.tracks)["actions"] ?? [];
    function length(name: string): number {
        return replay.lengths[name] ?? 0;
    }
    const pillTop = length("plate-bottom-top") + (length("badge-h") - length("pill-h")) / 2;
    return (
        Math.abs(bottom - bandBottom) <= 0.1 &&
        Math.abs(left - bandLeft) <= 0.1 &&
        right <= bandRight + 0.1 &&
        Math.abs(bottom - top - length("replay-b")) <= 0.1 &&
        (right <= length("plate-right-left") ||
            top >= pillTop + length("pill-h") - 2 ||
            bottom <= pillTop + 2) &&
        length("overlay-bottom") >= length("table-below") + replay.box.height - top
    );
}

/** Whether a desktop replay's controls stand at the right bar's foot under the cog, the panel's foot left as it is. */
function replayInColumn(replay: BoardGeometry): boolean {
    const { actions = [], corner = [], hand = [] } = slotAreas(replay.tracks);
    const [left = 0, top = 0, , bottom = 0] = actions;
    return (
        left >= (replay.lengths["col-right"] ?? Infinity) &&
        top >= (corner[1] ?? Infinity) + (replay.lengths["menu-size"] ?? 0) &&
        Math.abs(bottom - (hand[3] ?? Infinity)) <= 0.1 &&
        replay.lengths["overlay-bottom"] === 8
    );
}

/**
 * Whether a desktop's notices stand as toasts at 14px or more in the core's bottom-left corner: past the left strip's
 * lane, short of the bottom river's first tile, under the left river's longest reach (its sixth tile past a riichi
 * tile, the latest discard's gap and a tile's edge), over the left plate and the own row's melds' rise, a clamped toast
 * tall at least.
 */
function toastsPlace(geometry: BoardGeometry): boolean {
    const { lengths, tracks } = geometry;
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const toasts = slotAreas(tracks)["toasts"] ?? [];
    const [left = 0, top = 0, right = 0, bottom = 0] = toasts;
    const rw = length("rw");
    return (
        length("notice-text") >= 14 &&
        left >= length("col-left") + length("strip-depth") + SIDE_LANE_GAP &&
        right <= length("cx") - length("hx") &&
        top >=
            length("cy") -
                length("h") +
                (5 * rw + length("rh")) * LYING_Y_SHARE +
                length("latest-drop-gap") +
                TILE_EDGE_SHARE * rw &&
        bottom <= length("hand-top") - length("own-meld-rise") &&
        bottom - top >= 40
    );
}

/**
 * Where a desktop's decisions' band stands along the own row's top: from the bottom river's first tile, right of the
 * notices' toasts, to short of the right strip's lane, under the centre and the right river's first tile and its edge,
 * over the own row's melds' rise; its controls at least 40px tall with labels at least 14px.
 */
function bandPlace(geometry: BoardGeometry): Record<string, boolean> {
    const { lengths, tracks } = geometry;
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const areas = slotAreas(tracks);
    const [left = 0, top = 0, right = 0, bottom = 0] = areas["actions"] ?? [];
    const [, , toastsRight = Infinity] = areas["toasts"] ?? [];
    const riverStart = length("cx") - length("hx");
    return {
        clear:
            left >= toastsRight &&
            right <= length("col-right") - length("strip-depth") - SIDE_LANE_GAP &&
            top >= length("cy") + length("h") + TILE_EDGE_SHARE * length("rw") &&
            bottom <= length("hand-top") - length("own-meld-rise") &&
            bottom - top >= length("decision-h"),
        controls: length("decision-h") >= 40 && length("action-text") >= 14,
        fromRiverStart: Math.abs(left - riverStart) <= 0.1,
    };
}

/** Whether a strip's line holds four open kans and four added kans beside its hand's last two tiles, no deeper than its lane. */
function holdsFourKans(rooms: StripRooms, seat: StripSeat, depth: number): boolean {
    const line = seat === "top" ? rooms.top.anchor - rooms.top.start : rooms[seat].line;
    const openKan = { depth: UPRIGHT_DEPTH, units: 3 + SIDEWAYS_UNITS };
    const addedKan = { depth: 2, units: 2 + SIDEWAYS_UNITS };
    return [openKan, addedKan].every((kan) => {
        const laid = stripLayout(
            seat,
            { drawn: true, hand: 2, melds: [kan, kan, kan, kan] },
            rooms,
        );
        return (
            laid.depth <= depth + 0.001 &&
            laid.melds.every(
                ({ along, tile }) =>
                    along >= 0 &&
                    along + kan.units * (seat === "top" ? 1 : LYING_Y_SHARE) * tile <= line + 0.001,
            )
        );
    });
}

/**
 * Whether a desktop keeps every opponent's tile off its own row's span: the side strips' lanes at the centred table's
 * edges, an added kan's stack deep, outside the own row, which holds a full hand; the top strip between them; each side
 * line centred on the core where the table's height allows, or starting under the counters that stand over the left
 * lane and ending over the own plate's pill; and four kans on every line.
 */
function ownRowPlace({ box, lengths, strips, tracks }: BoardGeometry): Record<string, unknown> {
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const {
        hand = [],
        "strip-left": left = [],
        "strip-right": right = [],
        "strip-top": top = [],
    } = slotAreas(tracks);
    const tableHeight = lengths["table-h"] ?? box.height;
    const ownPill = length("hand-top") + length("oh") - length("pill-h");
    function centred([, lineTop = 0, , lineBottom = 0]: readonly number[]): boolean {
        const underCounters =
            lineTop >= length("counters-top") + length("counters-h") + 6 - 0.1 &&
            lineBottom <= ownPill + 0.1;
        return (
            Math.abs((lineTop + lineBottom) / 2 - length("cy")) <= 0.1 ||
            lineTop === 0 ||
            lineBottom === tableHeight ||
            underCounters
        );
    }
    const [leftInner = 0, rightInner = 0] = [left[2], right[0]];
    return {
        barsEqual: Math.abs(box.width - length("col-right") - length("col-left")) <= 0.001,
        kansOnLines: (["left", "right", "top"] as const).map(
            (seat) => strips !== null && holdsFourKans(strips, seat, length("strip-depth")),
        ),
        lanesAtEdges:
            Math.abs((left[0] ?? 0) - length("col-left")) <= 0.1 &&
            Math.abs((right[2] ?? 0) - length("col-right")) <= 0.1,
        lanesDeep:
            Math.min(leftInner - (left[0] ?? 0), (right[2] ?? 0) - rightInner) >= 2 * length("rw"),
        linesCentred: centred(left) && centred(right),
        rowBetweenLanes: (hand[0] ?? 0) >= leftInner && (hand[2] ?? Infinity) <= rightInner,
        rowHoldsHand: (hand[2] ?? 0) - (hand[0] ?? 0) >= FULL_HAND * length("ow") - 0.1,
        topBetweenLanes: (top[0] ?? 0) >= leftInner && (top[2] ?? Infinity) <= rightInner,
    };
}

type PillBox = Readonly<Record<"bottom" | "left" | "right" | "top", number>>;

/** The plates' pills (each plate's box less the tap box's padding) at their widest, by seat. */
function platePills({ box, lengths }: BoardGeometry): Readonly<Record<StripSeat | "own", PillBox>> {
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const pad = (length("badge-h") - length("pill-h")) / 2;
    const [width, height] = [length("plate-w"), length("pill-h")];
    const [leftEdge, rightEdge] = [
        box.width - length("plate-left-right"),
        length("plate-right-left"),
    ];
    const [upper, lower] = [length("plate-top-top") + pad, length("plate-bottom-top") + pad];
    function pill(left: number, top: number): PillBox {
        return { bottom: top + height, left, right: left + width, top };
    }
    return {
        left: pill(leftEdge - width, lower),
        own: pill(rightEdge, lower),
        right: pill(rightEdge, upper),
        top: pill(leftEdge - width, upper),
    };
}

/**
 * Whether the plates stand as one rectangle in the core's corners: the top seat's top-left, the right
 * seat's top-right, the left seat's bottom-left and the own one bottom-right, the left pair's right edges and the right
 * pair's left edges mirrored about the centre and each row's pills level; the left pair short of the top river's run-on
 * and the bottom river, the right pair past the top river and the bottom river's run-on; the top row above the centre
 * and the right river's reserved top, under the core's top; the bottom row under the centre and the left river's
 * reserve, above the own row's melds' rise; every pill between the side lanes, its box the control floor tall.
 */
function platesPlace(geometry: BoardGeometry): Record<string, boolean> {
    const { lengths } = geometry;
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const { left, own, right, top } = platePills(geometry);
    const [rw, rh, edge] = [length("rw"), length("rh"), TILE_EDGE_SHARE * length("rw")];
    const [cx, cy] = [length("cx"), length("cy")];
    const lane = length("strip-depth") + SIDE_LANE_GAP;
    return {
        bottomRow:
            left.top === own.top &&
            left.top >= cy + length("h") &&
            left.top >=
                cy -
                    length("h") +
                    (5 * rw + rh) * LYING_Y_SHARE +
                    length("latest-drop-gap") +
                    edge &&
            left.bottom <= length("hand-top") - length("own-meld-rise"),
        columns:
            left.right === top.right &&
            right.left === own.left &&
            Math.abs(cx - left.right - (right.left - cx)) <= 0.001 &&
            left.right <= Math.min(length("reach-top-left"), cx - length("hx")) &&
            right.left >= Math.max(length("reach-bottom-right"), cx + length("hx")),
        inLanes:
            left.left >= length("col-left") + lane - 0.001 &&
            right.right <= length("col-right") - lane + 0.001,
        tapFloor: length("badge-h") >= 40,
        topRow:
            top.top === right.top &&
            top.top >= length("core-top") - 0.001 &&
            top.bottom <= cy - length("h") &&
            top.bottom <=
                cy +
                    length("h") -
                    length("river-right-lift") -
                    (5 * rw + rh) * LYING_Y_SHARE -
                    length("latest-drop-gap"),
    };
}

/**
 * Whether a desktop's counters stand at the table's top-left corner, level with its top: ending at most a plate's gap
 * short of the left lane's inner edge above the left strip's line, or in the bar short of the strip, or on a barless
 * board 12px short of the top strip above the left strip's line; their dora in one row, 0.6 to 0.8 river tiles.
 */
function countersPlace(geometry: BoardGeometry): Record<string, boolean> {
    const { lengths, tracks } = geometry;
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const { "strip-left": stripLeft = [], "strip-top": stripTop = [] } = slotAreas(tracks);
    const laneInner = length("col-left") + length("strip-depth") + SIDE_LANE_GAP;
    const countersRight = length("counters-x") + length("counters-w");
    const countersBottom = length("counters-top") + length("counters-h");
    return {
        countersAtCorner:
            length("counters-top") === 0 &&
            length("counters-x") >= 6 &&
            (countersRight <= length("col-left") - 6 + 0.001 ||
                (countersRight <= laneInner - 6 + 0.1 &&
                    countersBottom <= (stripLeft[1] ?? 0) - 6 + 0.1) ||
                (geometry.arrangement !== "bars" &&
                    countersRight + 12 <= (stripTop[0] ?? 0) + 0.1 &&
                    countersBottom <= (stripLeft[1] ?? 0) - 6 + 0.1)),
        countersWhole:
            length("dora-w") >= 0.6 * length("rw") &&
            length("dora-w") <= 0.8 * length("rw") &&
            length("counters-w") >= 5 * length("dora-w") + 2 * length("dora-pad") - 0.001,
    };
}

/**
 * Whether a phone's felt is centred within rails that hold the cog, wider than its height's share only where a full
 * hand at the own floor or the column and its air needs it; its own row inside it with the gutter's air, the melds
 * ending at that air; the counters reaching its top-left edge; the cog and a one-column replay off it; and a replay's
 * panel clear of its controls.
 */
function feltPlaces(
    { box, lengths, tracks }: BoardGeometry,
    replay: BoardGeometry,
): Record<string, boolean> {
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const { corner = [], hand = [] } = slotAreas(tracks);
    const { actions = [] } = slotAreas(replay.tracks);
    const [replayLeft = 0] = actions;
    const [feltLeft, feltRight] = [length("felt-left"), length("felt-right")];
    const [handLeft = 0, , handRight = 0] = hand;
    const panelRight = box.width - (replay.lengths["overlay-right"] ?? 0);
    return {
        countersAtRim:
            length("counters-x") <= feltLeft + length("m") + 0.1 &&
            length("counters-x") + length("counters-w") >= feltLeft - 0.1,
        feltBounded:
            Math.abs(feltLeft + feltRight - box.width) <= 0.1 &&
            feltLeft >= length("m") + length("menu-size") &&
            (feltRight - feltLeft <= PHONE_FELT_BY_HEIGHT * box.height + 0.1 ||
                length("ow") <= PHONE_OWN_FLOOR ||
                Math.abs(
                    feltRight -
                        feltLeft -
                        (length("col-right") - length("col-left")) -
                        2 * PAGE_GUTTER,
                ) <= 0.1),
        ownRowInFelt:
            handLeft >= feltLeft + PAGE_GUTTER - 0.1 &&
            Math.abs(handRight - (feltRight - PAGE_GUTTER)) <= 0.1 &&
            handRight - handLeft >= FULL_HAND * length("ow") - 0.1,
        railsOffFelt:
            (corner[0] ?? 0) >= feltRight &&
            (replay.replay !== "column" || replayLeft >= feltRight),
        replayPanelClear: panelRight <= replayLeft - 8 + 0.1,
    };
}

/**
 * Whether a phone's board stands on its table column inside its felt: the left bar holding the counters at the face
 * floor or more, every control in a bar, the felt between each side lane and its river's reserve under three river
 * tiles, both side strips' lines a full hand long and ending above the own row, the centre at its least size; the felt
 * centred, within rails a control wide, no wider than the height's share (or a full hand at the own floor, or the column
 * and its air), the own row inside it with its air, its melds ending at that air; the cog and a replay's column in the
 * right rail off the felt.
 */
function phonePlaces(geometry: BoardGeometry): Record<string, boolean> {
    const { box, lengths, strips, tracks } = geometry;
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const areas = slotAreas(tracks);
    function area(slot: string): readonly number[] {
        return areas[slot] ?? [];
    }
    const [rw, colLeft, colRight] = [length("rw"), length("col-left"), length("col-right")];
    const [lane, rowTop] = [
        length("strip-depth") + SIDE_LANE_GAP,
        length("hand-top") - length("own-meld-rise"),
    ];
    const replay = boardGeometry({
        appliedEdges: NO_INSETS,
        box,
        safeInsets: NO_INSETS,
        slots: REPLAY_SLOTS,
    });
    const [replayLeft = 0, replayTop = 0, replayRight = 0] =
        slotAreas(replay.tracks)["actions"] ?? [];
    return {
        ...feltPlaces(geometry, replay),
        centreWhole: length("w") >= Math.max(RIVER_ROW_SIZE * rw, 100) && length("c") >= 68,
        controlsInBars: [area("field"), area("furiten"), area("switches")].every(
            ([, , right = Infinity]) => right <= colLeft,
        ),
        countersInLeftBar:
            length("counters-x") + length("counters-w") <= colLeft - 6 + 0.1 &&
            length("dora-w") >= FACE_FLOOR,
        feltUnderThreeTiles:
            length("reach-left") - (colLeft + lane) <= 3 * rw &&
            colRight - lane - length("reach-right") <= 3 * rw,
        fullHandAboveOwnRow:
            Math.min(strips?.left.line ?? 0, strips?.right.line ?? 0) >= length("full-reach") &&
            (area("strip-left")[3] ?? Infinity) <= rowTop,
        replayInRightBar:
            replayLeft >= colRight - 0.1 &&
            replayRight <= box.width - length("m") + 0.1 &&
            replayTop >= length("m") + length("menu-size"),
    };
}

/**
 * Whether a barless desktop lays its felt edge to edge: the cog over the right lane's top above the side lines, the
 * switches in the left lane, the side lines ending above the furiten mark over them, and the table centred in the
 * window, its spare height above and below it.
 */
function barlessPlaces({ box, lengths, tracks }: BoardGeometry): Record<string, boolean> {
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const areas = slotAreas(tracks);
    const lane = length("strip-depth") + SIDE_LANE_GAP;
    const [cogLeft = 0, cogTop = 0, cogRight = 0] = areas["corner"] ?? [];
    const [switchesLeft = 0, switchesTop = 0, switchesRight = 0] = areas["switches"] ?? [];
    const [, furitenTop = 0, , furitenBottom = 0] = areas["furiten"] ?? [];
    const spareAbove = length("table-top");
    const spareBelow = box.height - spareAbove - length("table-h");
    const linesEnd = Math.max(areas["strip-left"]?.[3] ?? 0, areas["strip-right"]?.[3] ?? 0);
    return {
        cogOverRightLane:
            cogLeft >= length("col-right") - lane - 0.001 &&
            cogRight <= length("col-right") + 0.001 &&
            cogTop + length("menu-size") <= length("lines-start"),
        feltEdgeToEdge: length("felt-left") <= 0 && length("felt-right") >= box.width,
        linesAboveFoot: linesEnd <= furitenTop && furitenBottom <= switchesTop,
        spareSplit: Math.min(spareAbove, spareBelow) > 0 && Math.abs(spareAbove - spareBelow) <= 1,
        switchesInLeftLane:
            switchesLeft >= length("col-left") - 0.001 &&
            switchesRight <= length("col-left") + lane + 0.001,
    };
}

function pocketEdges(
    lengths: Readonly<Record<string, number>>,
): Record<"bottom" | "left" | "right" | "top", number> {
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    return {
        bottom: length("cy") - length("h") - 6 - 0.3 * length("rw"),
        left: length("col-left") + length("strip-depth") + SIDE_LANE_GAP + 6 + 1.25 * length("rw"),
        right:
            Math.min(length("reach-top-left"), length("cx") - length("hx")) -
            6 -
            0.1 * length("rw"),
        top: length("m") + length("strip-depth") * LYING_Y_SHARE + 6,
    };
}

function pocketPlaces({ areas, box, lengths }: BoardGeometry): Record<string, boolean> {
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const pocket = pocketEdges(lengths);
    const { switches } = areas;
    const linesEnd = Math.max(areas["strip-left"]?.bottom ?? 0, areas["strip-right"]?.bottom ?? 0);
    return {
        feltEdgeToEdge: length("felt-left") <= 0 && length("felt-right") >= box.width,
        linesToOwnPill:
            linesEnd > (switches?.bottom ?? Infinity) &&
            linesEnd <= length("hand-top") + length("oh") - length("pill-h") - 2 + 0.001,
        switchesOnPocketFoot:
            Math.abs((switches?.bottom ?? 0) - pocket.bottom) < 0.001 &&
            Math.abs((switches?.left ?? 0) - pocket.left) < 0.001,
    };
}

describe("boardGeometry", () => {
    it.each([
        { chrome: "regular", family: "desktop", height: 900, width: 1440 },
        { chrome: "large", family: "desktop", height: 1440, width: 2560 },
        { chrome: "small", family: "desktop", height: 600, width: 800 },
        { chrome: "small", family: "desktop", height: 540, width: 1024 },
        { chrome: "small", family: "desktop", height: 900, width: 1100 },
        { chrome: "regular", family: "desktop", height: 900, width: 1120 },
        { chrome: "regular", family: "desktop", height: 657, width: 1366 },
        { chrome: "regular", family: "desktop", height: 540, width: 1280 },
        { chrome: "regular", family: "desktop", height: 770, width: 1440 },
    ])(
        "gives a $width x $height window a $family board with $chrome chrome in a 10px gutter, whichever is applied, its 6x4.5 centre and its own row at 1.2 to 1.45 river tiles (a full hand between the side strips' lanes) stacked from the top hand to the bottom edge, the height's slack between the top hand and the core",
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
                const rw = length("rw");
                const slackAbove =
                    length("core-top") - length("rh") - TOP_HAND_BACK_EDGE_SHARE * rw - 0.1 * rw;
                const slackBelow =
                    length("hand-top") - length("own-meld-rise") - length("river-foot");

                expect({
                    centre: [length("w"), length("c")],
                    handBetweenLanes: FULL_HAND * length("ow") <= rowBetweenLanes(lengths) + 0.001,
                    ownByRiver: ownTileByRiver(lengths),
                    ownRowOnBottom: length("hand-top") + length("oh") + ownRowDepth(lengths),
                    slackAbove: slackAbove >= -0.001 && slackBelow >= -0.001,
                }).toEqual({
                    centre: [RIVER_ROW_SIZE * rw, 4.5 * rw],
                    handBetweenLanes: true,
                    ownByRiver: true,
                    ownRowOnBottom: expect.closeTo(lengths["table-h"] ?? box.height, 6),
                    slackAbove: true,
                });
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
        [1280, 720, [39, 56, 83.42, 139.2]],
        [1366, 768, [42, 60, 87.02, 147]],
        [1920, 1080, [61, 88, 101.58, 181.6]],
        [2560, 1440, [82, 118, 138.09, 240.6]],
        [1440, 900, [50, 65, 98.83, 131.5]],
        [1280, 800, [44, 60, 89.64, 100]],
        [800, 600, [32, 44, 58.26, 0.8]],
        [960, 1080, [43, 52, 184.73, 0.4]],
        [1100, 1000, [49, 60, 149.96, 0]],
        [1280, 1024, [57, 70, 106.93, 1]],
        [1502, 1551, [68, 82, 183.27, 2.4]],
        [1024, 1366, [45, 55, 186.98, 6.5]],
    ])(
        "sizes a %ix%i desktop's river tile from its vertical stack and its own tile from its width, a full hand between the side strips' lanes, at most 1.45 river tiles, within bars that hold the switches named and the counters' row only while the own tile keeps 1.3 of the river tile, no bars where the width binds the river tile, the river tile no larger than leaves it 1.2, the table centred",
        (width, height, expected) => {
            const { lengths } = windowGeometry({ height, width });

            for (const [index, name] of SIZES.entries()) {
                expect(lengths[name], name).toBeCloseTo(expected[index] ?? Number.NaN, 1);
            }
        },
    );

    it.each([
        [816, 544, "bars"],
        [1024, 1366, "corner"],
        [800, 672, "pocket"],
    ])(
        "stands a width-bound %ix%i %s desktop's table no taller than its stack or its side strips' lines under the counters need, centred in the window: a barred one's own row hugging the bottom river and its top hand the core, the spare height lies above and below the table, every slot inside it",
        (width, height, arrangement) => {
            const geometry = windowGeometry({ height, width });
            const { box, lengths, tracks } = geometry;
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const table = length("table-h");
            const barless = geometry.arrangement !== "bars";
            const slotBottoms = Object.values(slotAreas(tracks)).map((area) => area[3] ?? 0);
            const spareAbove = length("table-top");
            const spareBelow = box.height - spareAbove - table;

            expect(geometry.arrangement).toBe(arrangement);
            expect({
                ownRowOnTableBottom: length("hand-top") + length("oh") + ownRowDepth(lengths),
                ownRowToCore:
                    length("hand-top") - length("own-meld-rise") - length("river-foot") < 1 ||
                    barless,
                slotsInTable: Math.max(...slotBottoms) <= table,
                spareOutside: Math.min(spareAbove, spareBelow) > 0,
                spareSplit: Math.abs(spareAbove - spareBelow) <= 1,
                topHandToCore:
                    length("core-top") - length("rh") - TOP_HAND_BACK_EDGE_SHARE * length("rw") <
                        0.5 * length("rw") || barless,
            }).toEqual({
                ownRowOnTableBottom: expect.closeTo(table, 6),
                ownRowToCore: true,
                slotsInTable: true,
                spareOutside: true,
                spareSplit: true,
                topHandToCore: true,
            });
        },
    );

    it.each([
        { across: 1366, axis: "height", ends: [33, 61] },
        { across: 1920, axis: "height", ends: [33, 73] },
        { across: 768, axis: "width", ends: [33, 42] },
        { across: 1080, axis: "width", ends: [35, 61] },
    ])(
        "never shrinks a desktop's river tile as its window grows in $axis from $across across",
        ({ across, axis, ends }) => {
            const tiles = Array.from({ length: 701 }, (_unused, step) => {
                const along = 600 + step;
                const box =
                    axis === "height"
                        ? { height: along, width: across }
                        : { height: across, width: along + 200 };
                return windowGeometry(box).lengths["rw"] ?? 0;
            });

            expect(tiles.filter((rw, step) => rw < (tiles[step - 1] ?? 0))).toEqual([]);
            expect([tiles[0], tiles.at(-1)]).toEqual(ends);
        },
    );

    it("never drops a phone's own tile by more than the river's 2px give as its window grows in height across the old cliff at 800 across", () => {
        const owns = Array.from(
            { length: 61 },
            (_unused, step) =>
                windowGeometry({ height: 380 + step, width: 800 }).lengths["ow"] ?? 0,
        );

        expect(
            owns.filter((ow, step) => ow < (owns[step - 1] ?? 0) - PHONE_OWN_GIVEN_FOR_RIVER),
        ).toEqual([]);
    });

    it("keeps a 770 x 300 phone's band holding the widest prompt at the tap-floor range's own tile rather than a larger own tile without it", () => {
        const { lengths, tracks } = windowGeometry({ height: 300, width: 770 });
        const [left = 0, top = 0, right = 0, bottom = 0] = slotAreas(tracks)["actions"] ?? [];

        expect({ ow: lengths["ow"], rw: lengths["rw"] }).toEqual({ ow: 36, rw: 13 });
        expect(bottom - top).toBeGreaterThanOrEqual(
            phonePromptHeight(right - left, lengths["timer-w"] ?? 0) - 0.001,
        );
    });

    it.each([
        { height: 375, pinned: { ow: 37, rw: 19 }, width: 667 },
        { height: 390, pinned: { ow: 37, rw: 19 }, width: 667 },
        { height: 354, pinned: { ow: 39, rw: 20 }, width: 724 },
        { height: 360, pinned: { ow: 42, rw: 20 }, width: 800 },
        { height: 390, pinned: { ow: 43, rw: 22 }, width: 750 },
        { height: 379, pinned: { ow: 44, rw: 21 }, width: 761 },
        { height: 414, pinned: { "dora-w": 15, ow: 47, rw: 23 }, width: 808 },
        { height: 480, pinned: { ow: 49, rw: 26 }, width: 850 },
        { height: 430, pinned: { "dora-w": 15, ow: 51, rw: 24 }, width: 932 },
        { height: 414, pinned: { "dora-w": 15, ow: 49, rw: 23 }, width: 1000 },
        { height: 500, pinned: { ow: 59, rw: 28 }, width: 1024 },
    ])(
        "sizes a $width x $height window's phone board's tiles jointly in its felt: the own row inside it with its air, the felt bounded by the height and its rails, the left bar holding the counters, the side strips' lines a full hand long above the own row, the felt beside each side river under three river tiles, every control in a bar, the cog and a replay's column in the right rail off the felt",
        ({ height, pinned, width }) => {
            const geometry = windowGeometry({ height, width });
            const { lengths } = geometry;

            for (const [name, value] of Object.entries(pinned)) {
                expect(lengths[name], name).toBeCloseTo(value, 2);
            }
            expect(phonePlaces(geometry)).toEqual({
                centreWhole: true,
                controlsInBars: true,
                countersAtRim: true,
                countersInLeftBar: true,
                feltBounded: true,
                feltUnderThreeTiles: true,
                fullHandAboveOwnRow: true,
                ownRowInFelt: true,
                railsOffFelt: true,
                replayInRightBar: true,
                replayPanelClear: true,
            });
        },
    );

    it.each([
        [667, 375],
        [1440, 900],
        [1366, 657],
        [390, 844],
    ])(
        "reserves twenty discards and the latest gap, deeper by the tile edge along the light off a phone (the top river's gap too, past its rows' edge), in a %ix%i window without reserving a longer third row",
        (width, height) => {
            const { family, lengths } = windowGeometry({ height, width });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const across = length("g") + 4 * length("rh") + LATEST_DISCARD_GAP;
            const runOn = 7 * length("rw") + length("rh") + LATEST_DISCARD_GAP;
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
                "reach-top-row3":
                    length("cy") -
                    length("h") -
                    (lengths["g-top"] ?? length("g")) -
                    2 * length("rh") * LYING_Y_SHARE,
            };

            for (const [name, reach] of Object.entries(expected)) {
                expect(length(name), name).toBeCloseTo(reach, 3);
            }
            expect(
                Math.min(
                    length("cy") +
                        length("h") -
                        (5 * length("rw") + length("rh")) * LYING_Y_SHARE -
                        length("latest-drop-gap"),
                    length("reach-top-row3") -
                        length("rh") * LYING_Y_SHARE -
                        length("latest-drop-gap"),
                ),
            ).toBeGreaterThanOrEqual(length("core-top") - 0.001);
        },
    );

    it("gives an empty box no sizes", () => {
        expect(windowGeometry({ height: 0, width: 0 }).lengths).toEqual({});
    });
});

describe("boardGeometry's rivers", () => {
    it.each([
        [667, 375],
        [1366, 657],
        [1728, 988],
        [2560, 1440],
    ])(
        "keeps the right river's first tile's edge clear above the bottom river, whose first row a sideways tile runs past the centre's corner, in a %ix%i window",
        (width, height) => {
            const { lengths } = windowGeometry({ height, width });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const centreFoot = length("cy") + length("h");
            const rightEdgeFoot =
                centreFoot - length("river-right-lift") + TILE_EDGE_SHARE * length("rw");

            expect(centreFoot + length("g") - rightEdgeFoot).toBeGreaterThanOrEqual(2);
        },
    );

    it("steps a 1440x900 desktop's top and bottom rivers' rows by the oblique face and reserves a tile's edge only past the bottom river's last row", () => {
        const { lengths } = windowGeometry({ height: 900, width: 1440 });
        function length(name: string): number {
            return lengths[name] ?? Number.NaN;
        }
        const rows = 3 * length("rh") * LYING_Y_SHARE;

        expect(length("river-across")).toBeCloseTo(rows, 6);
        expect(length("river-foot")).toBeCloseTo(
            length("cy") +
                length("h") +
                length("g") +
                rows +
                length("latest-drop-gap") +
                Math.round(TILE_EDGE_SHARE * length("rw")),
            6,
        );
    });

    it("lays a 1440x900 desktop's side river's six tiles along 6 x 0.85 river tiles and its rows across at a tile's whole length", () => {
        const { lengths } = windowGeometry({ height: 900, width: 1440 });
        const rw = lengths["rw"] ?? Number.NaN;

        expect([lengths["side-river-along"], lengths["side-river-across"]]).toEqual([
            expect.closeTo(6 * 0.85 * rw, 6),
            expect.closeTo(3 * (lengths["rh"] ?? Number.NaN), 6),
        ]);
    });
});

describe("boardGeometry's strips", () => {
    it.each([
        [1920, 1080],
        [1920, 950],
        [1726, 1000],
        [1536, 864],
        [1536, 730],
        [1440, 900],
        [1440, 790],
        [1366, 768],
        [1366, 650],
        [1280, 720],
        [1280, 620],
        [1280, 800],
        [1680, 1050],
        [2560, 1440],
        [2560, 1300],
        [1502, 1551],
        [960, 1000],
        [1280, 1024],
        [1024, 768],
    ])(
        "stands no opponent's tile above a %ix%i desktop's own row: the side strips at the centred table's edges, their lanes an added kan's stack deep outside the own row's span, the top strip between them, each line centred on the core and holding four open kans",
        (width, height) => {
            expect(ownRowPlace(windowGeometry({ height, width }))).toEqual({
                barsEqual: true,
                kansOnLines: [true, true, true],
                lanesAtEdges: true,
                lanesDeep: true,
                linesCentred: true,
                rowBetweenLanes: true,
                rowHoldsHand: true,
                topBetweenLanes: true,
            });
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
                origin -
                    (oldest?.along ?? Number.NaN) -
                    pon.units * LYING_Y_SHARE * (oldest?.tile ?? Number.NaN),
            ).toBeGreaterThanOrEqual(0);
        },
    );

    it.each([
        { foot: "rail", form: "letters", height: 375, width: 667 },
        { foot: "rail", form: "letters", height: 414, width: 896 },
        { foot: "rail", form: "block", height: 331, width: 891 },
        { foot: "line", form: "block", height: 236, width: 667 },
    ])(
        "stands a $width x $height phone's play switches as $form at the $foot's foot, by the screen's edge in a rail, the counters at the top and the notices' field over the furiten mark between them",
        ({ foot, form, height, width }) => {
            const { lengths, switches, tracks } = windowGeometry({ height, width });
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const areas = slotAreas(tracks);
            const [switchesLeft = 0, switchesTop = 0, switchesRight = 0, switchesBottom = 0] =
                areas["switches"] ?? [];
            const [, fieldTop = 0, , fieldBottom = 0] = areas["field"] ?? [];
            const [, furitenTop = 0, furitenRight = 0, furitenBottom = 0] = areas["furiten"] ?? [];
            const columns = form === "block" ? 2 : 1;

            expect(switches).toBe(form);
            expect(tenths([switchesRight - switchesLeft, switchesBottom - switchesTop])).toEqual(
                tenths([columns * length("switch-h"), (4 / columns) * length("switch-h")]),
            );
            expect({
                atFoot:
                    Math.abs(
                        switchesBottom -
                            (foot === "rail" ? height - length("m") : length("lines-end")),
                    ) <= 0.1,
                countersAbove: length("counters-top") + length("counters-h") <= fieldTop,
                fieldAboveFuriten: fieldBottom <= furitenTop,
                furitenAboveSwitches: furitenBottom <= switchesTop,
                furitenInBar: furitenRight <= length("col-left"),
                inRail:
                    foot !== "rail" ||
                    (switchesLeft === length("m") &&
                        switchesRight <= length("felt-left") - 4 + 0.1),
            }).toEqual({
                atFoot: true,
                countersAbove: true,
                fieldAboveFuriten: true,
                furitenAboveSwitches: true,
                furitenInBar: true,
                inRail: true,
            });
        },
    );

    it("names the play switches at the plates' text where the bar holds it, never under 14px or three quarters of it, nor smaller on a larger board", () => {
        const boards = [
            [1280, 720],
            [1366, 768],
            [1536, 864],
            [1920, 1080],
            [2560, 1440],
        ].map(([width = 0, height = 0]) => windowGeometry({ height, width }, 10).lengths);
        const labels = boards.map((lengths) => lengths["switch-name-text"] ?? 0);

        expect(
            labels.map(
                (label, index) =>
                    label >= Math.max(14, 0.75 * (boards[index]?.["text"] ?? Infinity)) &&
                    label >= (labels[index - 1] ?? 0),
            ),
        ).toEqual([true, true, true, true, true]);
        expect(labels.at(-1)).toBeCloseTo(boards.at(-1)?.["text"] ?? 0);
    });

    it.each([
        { height: 720, switches: "names", width: 1280 },
        { height: 600, switches: "names", width: 1366 },
        { height: 1080, switches: "names", width: 1920 },
        { height: 900, switches: "names", width: 1440 },
        { height: 800, switches: "letters", width: 1280 },
        { height: 1440, switches: "names", width: 2560 },
        { height: 1440, switches: "names", width: 3440 },
        { height: 576, switches: "letters", width: 960 },
        { height: 544, switches: "letters", width: 864 },
    ])(
        "keeps a $width x $height desktop's controls in the bars: the counters over the field, furiten and $switches switches down the left one to the own row's foot, the cog in the right one near the column, every bar's control off the felt, whose air beside the column gives way to them, the panel in the column, and the notices' toasts in the core's bottom-left corner",
        ({ height, switches, width }) => {
            const live = windowGeometry({ height, width });
            const { box } = live;
            const replay = replayOf(live);
            function length(name: string): number {
                return live.lengths[name] ?? Number.NaN;
            }
            const { field, furiten, switches: switchesArea } = slotAreas(live.tracks);
            const { corner } = slotAreas(replay.tracks);
            const [colLeft, colRight] = [length("col-left"), length("col-right")];
            function panel(lengths: Readonly<Record<string, number>>): (number | undefined)[] {
                return [lengths["overlay-left"], lengths["overlay-right"]];
            }

            expect({
                barsOffFelt:
                    (switchesArea?.[2] ?? Infinity) <= length("felt-left") + 0.1 &&
                    ((corner?.[0] ?? 0) + (corner?.[2] ?? 0) - length("menu-size")) / 2 >=
                        length("felt-right") - 0.1 &&
                    length("felt-left") >= colLeft - PAGE_GUTTER - 0.1 &&
                    (replay.replay === "row" ||
                        (slotAreas(replay.tracks)["actions"]?.[0] ?? 0) >=
                            (replay.lengths["felt-right"] ?? Infinity) - 0.1),
                countersOverField:
                    length("counters-top") + length("counters-h") <= (field?.[1] ?? 0),
                form: live.switches,
                leftBar: [field, furiten, switchesArea].every(
                    (area) => (area?.[0] ?? -1) >= 0 && (area?.[2] ?? Infinity) <= colLeft,
                ),
                leftBarDown:
                    (field?.[3] ?? Infinity) <= (furiten?.[1] ?? 0) &&
                    (furiten?.[3] ?? Infinity) <= (switchesArea?.[1] ?? 0),
                panel: [panel(live.lengths), panel(replay.lengths)],
                rightBar: (corner?.[0] ?? 0) >= colRight,
                rightBarNearColumn:
                    (corner?.[2] ?? Infinity) <= colRight + 6 + 6 * length("rw") + 0.1,
                switchesOverRowFoot:
                    (switchesArea?.[3] ?? Infinity) <=
                    length("hand-top") + length("oh") - length("pill-h") - 6 + 0.1,
                switchesWide:
                    (switchesArea?.[2] ?? 0) -
                    (switchesArea?.[0] ?? 0) -
                    (switches === "names" ? length("switch-label-w") : length("switch-h")),
                toasts: toastsPlace(live),
            }).toEqual({
                barsOffFelt: true,
                countersOverField: true,
                form: switches,
                leftBar: true,
                leftBarDown: true,
                panel: [
                    [colLeft + 8, box.width - colRight + 8],
                    [
                        (replay.lengths["col-left"] ?? 0) + 8,
                        box.width - (replay.lengths["col-right"] ?? 0) + 8,
                    ],
                ],
                rightBar: true,
                rightBarNearColumn: true,
                switchesOverRowFoot: true,
                switchesWide: expect.closeTo(0, 0),
                toasts: true,
            });
            expect(
                Object.values(slotAreas(live.tracks)).filter(
                    ([areaLeft, areaTop, areaRight, areaBottom]) =>
                        !(areaLeft < areaRight && areaTop < areaBottom),
                ),
            ).toEqual([]);
        },
    );

    it.each([
        { form: "row", height: 720, width: 1280 },
        { form: "row", height: 657, width: 1366 },
        { form: "row", height: 1080, width: 1920 },
        { form: "row", height: 1440, width: 3440 },
        { form: "row", height: 768, width: 1024 },
        { form: "pairs", height: 600, width: 800 },
    ])(
        "stands a $width x $height desktop replay's controls as $form: a row along the decisions' band's foot from the bottom river's start, off the own pill, the panel above it, else a bar's two paired columns at its foot",
        ({ form, height, width }) => {
            const live = windowGeometry({ height, width }, 10);
            const replay = replayOf(live);
            const side = replay.lengths["replay-b"] ?? 0;
            const most = Math.max(replay.lengths["ow"] ?? 0, replay.lengths["moves-h"] ?? 0);

            expect({
                control: side >= 40 && side <= most,
                form: replay.replay,
                placed: form === "row" ? replayInRow(live, replay) : replayInColumn(replay),
            }).toEqual({ control: true, form, placed: true });
        },
    );
});

describe("boardGeometry's decisions", () => {
    it.each([
        { height: 1080, width: 1920 },
        { height: 900, width: 1440 },
        { height: 768, width: 1366 },
        { height: 657, width: 1366 },
        { height: 720, width: 1280 },
        { height: 1551, width: 1502 },
        { height: 1000, width: 960 },
        { height: 600, width: 800 },
    ])(
        "stands a $width x $height live desktop's decisions in a band along the own row's top from the bottom river's first tile, right of the toasts, under the centre and the right river, short of the right strip's lane, its controls 40px tall or more",
        ({ height, width }) => {
            expect(bandPlace(windowGeometry({ height, width }, 10))).toEqual({
                clear: true,
                controls: true,
                fromRiverStart: true,
            });
        },
    );

    it("keeps a 640x308 phone's decisions band as wide as it stands without the top river's edge room, from the left strip's lane under the centre", () => {
        const { lengths, tracks } = windowGeometry({ height: 308, width: 640 });
        const [left = 0, top = 0, right = 0] = slotAreas(tracks)["actions"] ?? [];

        expect(right - left).toBeCloseTo(354.6, 1);
        expect(left).toBeLessThan((lengths["cx"] ?? 0) - (lengths["hx"] ?? 0));
        expect(top).toBeGreaterThanOrEqual((lengths["cy"] ?? 0) + (lengths["h"] ?? 0));
    });

    it.each([
        { fromLane: true, height: 375, insets: NO_INSETS, rows: 2, width: 667 },
        { fromLane: true, height: 390, insets: NO_INSETS, rows: 2, width: 750 },
        { fromLane: true, height: 430, insets: NO_INSETS, rows: 2, width: 932 },
        {
            fromLane: true,
            height: 275,
            insets: { ...NO_INSETS, left: 44, right: 44 },
            rows: 1,
            width: 896,
        },
        { fromLane: true, height: 331, insets: NO_INSETS, rows: 2, width: 891 },
    ])(
        "stands a $width x $height live phone's decisions in a band along the own row's top, short of both side strips' lanes, 4px under the centre and the right river's first tiles, its bottom row under the left river's longest reach or the band from the centre's left edge, $rows row(s) of 40px controls tall, as many as the widest prompt takes at its width",
        ({ fromLane, height, insets, rows, width }) => {
            const { family, lengths, tracks } = windowGeometry({ height, width }, 0, insets);
            function length(name: string): number {
                return lengths[name] ?? Number.NaN;
            }
            const [left = 0, top = 0, right = 0, bottom = 0] = slotAreas(tracks)["actions"] ?? [];
            const lane = length("strip-depth") + SIDE_LANE_GAP;
            const leftRiverEnd =
                length("cy") -
                length("h") +
                (5 * length("rw") + length("rh")) * LYING_Y_SHARE +
                LATEST_DISCARD_GAP;
            const centreLeft = length("cx") - length("hx");

            expect(family).toBe("phone");
            expect({
                clear:
                    left >= length("col-left") + lane &&
                    right <= length("col-right") - lane &&
                    top >= length("cy") + length("h") + 4 - 0.1 &&
                    bottom <= length("hand-top") - length("own-meld-rise") &&
                    (bottom - 40 >= leftRiverEnd - 0.1 || left >= centreLeft - 0.1),
                fromLane: left < centreLeft,
                holdsWidestPrompt:
                    right - left >=
                    (rows === 1 ? WIDEST_PROMPT_IN_ONE_ROW : WIDEST_PROMPT_FIRST_OF_TWO_ROWS),
                rows: Math.floor((bottom - top + 2) / 42),
            }).toEqual({ clear: true, fromLane, holdsWidestPrompt: true, rows });
        },
    );

    it("sizes a desktop's decision controls from its river tile, 0.85 of it and never under 40px, so a larger window never draws them smaller", () => {
        const boards = [
            [1280, 720],
            [1920, 1080],
            [2560, 1440],
            [3440, 1440],
        ].map(([width = 0, height = 0]) => windowGeometry({ height, width }, 10).lengths);
        const heights = boards.map((lengths) => lengths["decision-h"] ?? 0);

        expect(heights).toEqual([40, 51, 69, 69]);
        expect(heights).toEqual(
            boards.map((lengths) => Math.max(40, Math.floor(0.85 * (lengths["rw"] ?? 0)))),
        );
    });
});

describe("boardGeometry's plates", () => {
    it.each([
        [1280, 720],
        [1366, 768],
        [1440, 900],
        [1920, 1080],
        [2560, 1440],
        [1024, 768],
        [1366, 657],
        [1280, 632],
        [1366, 550],
        [800, 600],
        [1502, 1551],
        [960, 1000],
        [667, 375],
        [844, 390],
        [932, 430],
        [896, 275],
        [891, 331],
        [808, 275],
        [844, 251],
    ])(
        "stands a %ix%i board's plates as one rectangle in the core's corners, mirrored about the centre, clear of every river's reserve and the side lanes",
        (width, height) => {
            expect(platesPlace(windowGeometry({ height, width }))).toEqual({
                bottomRow: true,
                columns: true,
                inLanes: true,
                tapFloor: true,
                topRow: true,
            });
        },
    );

    it.each([
        [1280, 720],
        [1440, 900],
        [2560, 1440],
        [1024, 768],
        [1366, 550],
        [800, 600],
        [1502, 1551],
    ])(
        "stands a %ix%i desktop's counters' dora in one row of 0.6 to 0.8 river tiles at the table's top-left corner",
        (width, height) => {
            expect(countersPlace(windowGeometry({ height, width }, 10))).toEqual({
                countersAtCorner: true,
                countersWhole: true,
            });
        },
    );
});

describe("boardGeometry without bars", () => {
    it.each([
        [1502, 1551],
        [1024, 1366],
        [960, 1080],
    ])(
        "lays a width-bound %ix%i desktop's felt edge to edge with no bars: the cog over the right lane's top and the switches and furiten in the left lane's foot, the side strips' lines between the counters and the switches, the table centred in the window, its spare height above and below it",
        (width, height) => {
            expect(barlessPlaces(windowGeometry({ height, width }))).toEqual({
                cogOverRightLane: true,
                feltEdgeToEdge: true,
                linesAboveFoot: true,
                spareSplit: true,
                switchesInLeftLane: true,
            });
        },
    );

    it.each([
        { arrangement: "pocket", height: 768, rw: 42, width: 1024 },
        { arrangement: "corner", height: 660, rw: 22, width: 580 },
    ])(
        "lays a $width x $height desktop out barless in the arrangement that reaches the larger river tile, the corner where the pocket does not hold its controls: $arrangement at $rw",
        ({ arrangement, height, rw, width }) => {
            const geometry = windowGeometry({ height, width });

            expect([geometry.arrangement, geometry.lengths["rw"]]).toEqual([arrangement, rw]);
        },
    );

    it("lays a 1024x768 pocket desktop's felt edge to edge, its play switches at the pocket's bottom-left and its side strips' lines down to the own pill", () => {
        expect(pocketPlaces(windowGeometry({ height: 768, width: 1024 }))).toEqual({
            feltEdgeToEdge: true,
            linesToOwnPill: true,
            switchesOnPocketFoot: true,
        });
    });

    it("keeps a width-bound 864x736 pocket desktop's switches, furiten and field in the pocket of its shortened table, live and replay", () => {
        const live = windowGeometry({ height: 736, width: 864 });
        for (const geometry of [live, replayOf(live)]) {
            const pocket = pocketEdges(geometry.lengths);
            const stack = [
                geometry.areas["switches"],
                geometry.areas["furiten"],
                geometry.areas["field"],
            ];

            expect({
                arrangement: geometry.arrangement,
                shortened: (geometry.lengths["table-h"] ?? Infinity) < geometry.box.height,
                stackInPocket: stack.every(
                    (area) =>
                        area !== undefined &&
                        area.left >= pocket.left - 0.001 &&
                        area.right <= pocket.right + 0.001 &&
                        area.top >= pocket.top - 0.001 &&
                        area.bottom <= pocket.bottom + 0.001 &&
                        area.top < area.bottom,
                ),
            }).toEqual({ arrangement: "pocket", shortened: true, stackInPocket: true });
        }
    });
});

const AUDIT_WIDTHS = Array.from({ length: 56 }, (_unused, step) => 800 + 32 * step);

const AUDIT_HEIGHTS = Array.from({ length: 34 }, (_unused, step) => 544 + 32 * step);

const AUDIT_SLOTS = [LIVE_SLOTS, REPLAY_SLOTS] as const;

const FAMILY_EDGE = [PHONE_HEIGHT + 2 * PAGE_GUTTER - 1, PHONE_HEIGHT + 2 * PAGE_GUTTER] as const;

function crossing(axis: "height" | "width", threshold: number, across: number): BoardBox[] {
    return Array.from({ length: 33 }, (_unused, step) => {
        const along = threshold + 2 * PAGE_GUTTER - 16 + step;
        return axis === "height"
            ? { height: along, width: across }
            : { height: across, width: along };
    });
}

const AUDIT_LINES: readonly (readonly BoardBox[])[] = [
    ...AUDIT_HEIGHTS.map((height) => AUDIT_WIDTHS.map((width) => ({ height, width }))),
    ...AUDIT_WIDTHS.map((width) => AUDIT_HEIGHTS.map((height) => ({ height, width }))),
    ...[640, 900, 1200].map((height) => crossing("width", SMALL_CHROME_WIDTH, height)),
    ...[1240, 1440, 1600].map((height) => crossing("width", LARGE_CHROME_WIDTH, height)),
    ...[2100, 2400, 2560].map((width) => crossing("height", LARGE_CHROME_HEIGHT, width)),
];

function auditInput(window: BoardBox, slots: BoardSlots): BoardInput {
    return { appliedEdges: NO_INSETS, box: window, safeInsets: NO_INSETS, slots };
}

const auditSolved = new Map<string, BoardGeometry>();

function audited(window: BoardBox, slots: BoardSlots): BoardGeometry {
    const key = `${window.width}x${window.height} ${slots.band}`;
    const solved = auditSolved.get(key) ?? boardGeometry(auditInput(window, slots));
    auditSolved.set(key, solved);
    return solved;
}

function auditedBoards(): readonly (readonly [string, BoardGeometry])[] {
    const windows = new Map(
        [
            ...AUDIT_LINES.flat(),
            ...AUDIT_WIDTHS.map((width) => ({ height: FAMILY_EDGE[1], width })),
        ].map((window) => [`${window.width}x${window.height}`, window]),
    );
    return AUDIT_SLOTS.flatMap((slots) =>
        [...windows].map(
            ([size, window]) => [`${size} (${slots.band})`, audited(window, slots)] as const,
        ),
    );
}

const UNPLACED: BoardRect = {
    bottom: Number.NaN,
    left: Number.NaN,
    right: Number.NaN,
    top: Number.NaN,
};

function tileReserves(geometry: BoardGeometry): readonly (readonly [string, BoardRect])[] {
    const { areas, lengths, strips } = geometry;
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const lane = length("strip-depth") + SIDE_LANE_GAP;
    const start = length("lines-start");
    function line(seat: "left" | "right"): number {
        return start + Math.max(length("full-reach"), strips?.[seat].line ?? Number.NaN);
    }
    return [
        [
            "left line",
            {
                bottom: line("left"),
                left: length("col-left"),
                right: length("col-left") + lane,
                top: start,
            },
        ],
        [
            "right line",
            {
                bottom: line("right"),
                left: length("col-right") - lane,
                right: length("col-right"),
                top: start,
            },
        ],
        ["top strip", areas["strip-top"] ?? UNPLACED],
        [
            "centre",
            {
                bottom: length("cy") + length("h"),
                left: length("cx") - length("hx"),
                right: length("cx") + length("hx"),
                top: length("cy") - length("h"),
            },
        ],
        ...Object.entries(riverReserves(geometry)),
    ];
}

function barlessControls(
    geometry: BoardGeometry,
): readonly (readonly [string, BoardRect | undefined])[] {
    const { areas, arrangement, lengths } = geometry;
    function length(name: string): number {
        return lengths[name] ?? Number.NaN;
    }
    const fixed = [
        [
            "counters",
            {
                bottom: length("counters-top") + length("counters-h"),
                left: length("counters-x"),
                right: length("counters-x") + length("counters-w"),
                top: length("counters-top"),
            },
        ],
        ["cog", cogSquare(geometry)],
    ] as const;
    return arrangement === "pocket"
        ? [
              ...fixed,
              ...(["switches", "furiten", "field"] as const).map(
                  (slot) => [slot, areas[slot]] as const,
              ),
          ]
        : fixed;
}

function overlaps(first: BoardRect, second: BoardRect): boolean {
    return (
        first.left < second.right &&
        second.left < first.right &&
        first.top < second.bottom &&
        second.top < first.bottom
    );
}

function inTable(rect: BoardRect, { box, lengths }: BoardGeometry): boolean {
    return (
        rect.left >= -0.001 &&
        rect.top >= -0.001 &&
        rect.right <= box.width + 0.001 &&
        rect.bottom <= (lengths["table-h"] ?? box.height) + 0.001
    );
}

const CONTROL_SLOTS = ["switches", "furiten", "field", "corner", "actions"] as const;

function controlAreaFaults(geometry: BoardGeometry): string[] {
    const tracked = slotAreas(geometry.tracks);
    return CONTROL_SLOTS.flatMap((slot) => {
        const area = geometry.areas[slot];
        if (area === undefined) {
            return [];
        }
        const edges = [area.left, area.top, area.right, area.bottom];
        const lines = tracked[slot] ?? [];
        return [
            edges.every(Number.isFinite) && area.left < area.right && area.top < area.bottom
                ? []
                : [`${slot} not a box`],
            inTable(area, geometry) ? [] : [`${slot} off the table`],
            tenths(edges).every(
                (edge, index) => Math.abs(edge - (lines[index] ?? Number.NaN)) <= 0.11,
            )
                ? []
                : [`${slot} off its tracks`],
        ].flat();
    });
}

describe("boardGeometry over desktop windows 32px apart and 1px across the chrome tiers' edges", () => {
    it("never shrinks the river tile from a window to its wider or taller neighbour, live and replay", () => {
        const shrinks = AUDIT_SLOTS.flatMap((slots) =>
            AUDIT_LINES.flatMap((line) =>
                line.slice(1).flatMap((window, step) => {
                    const before = line[step] ?? window;
                    const [smaller = Number.NaN, larger = Number.NaN] = [
                        audited(before, slots),
                        audited(window, slots),
                    ].map(({ lengths }) => lengths["rw"]);
                    if (larger >= smaller) {
                        return [];
                    }
                    const misfits = desktopPlanMisfits(auditInput(window, slots), smaller).map(
                        ({ misfits: why, plan }, order) =>
                            `${order + 1}. ${plan.arrangement}/${plan.counters}/${plan.bar}: ${why.join(",") || "none"}`,
                    );
                    return [
                        `rw ${smaller} at ${before.width}x${before.height} -> ${larger} at ${window.width}x${window.height} (${slots.band}); full-height misfits at rw ${smaller}: ${misfits.join("; ")}`,
                    ];
                }),
            ),
        );

        expect(shrinks).toStrictEqual([]);
    });

    it("keeps a barless desktop's counters, cog and pocket controls in its table, off the side lines' full reach, the top strip, the centre and the rivers' reserves, live and replay", () => {
        const barless = auditedBoards().filter(
            ([, geometry]) =>
                geometry.arrangement === "corner" || geometry.arrangement === "pocket",
        );
        const covered = barless.flatMap(([size, geometry]) => {
            const reserves = tileReserves(geometry);
            return barlessControls(geometry).flatMap(([control, rect]) =>
                rect === undefined
                    ? [`${control} missing at ${size}`]
                    : [
                          ...(inTable(rect, geometry)
                              ? []
                              : [`${control} off the table at ${size}`]),
                          ...reserves
                              .filter(
                                  ([, reserve]) =>
                                      !Object.values(reserve).every(Number.isFinite) ||
                                      overlaps(rect, reserve),
                              )
                              .map(([reserve]) => `${control} on ${reserve} at ${size}`),
                      ],
            );
        });

        expect(new Set(barless.map(([, geometry]) => geometry.arrangement))).toStrictEqual(
            new Set(["corner", "pocket"]),
        );
        expect(covered).toStrictEqual([]);
    });

    it("lays every occupied control area as a box inside the table on the tracks' lines, either side of the family switch", () => {
        const phoneSide = AUDIT_SLOTS.flatMap((slots) =>
            AUDIT_WIDTHS.map(
                (width) =>
                    [
                        `${width}x${FAMILY_EDGE[0]} (${slots.band})`,
                        audited({ height: FAMILY_EDGE[0], width }, slots),
                    ] as const,
            ),
        );
        const boards = [...auditedBoards(), ...phoneSide];
        const faults = boards.flatMap(([size, geometry]) =>
            controlAreaFaults(geometry).map((fault) => `${fault} at ${size} (${geometry.family})`),
        );
        const occupied = boards.flatMap(([, { areas }]) =>
            CONTROL_SLOTS.filter((slot) => areas[slot] !== undefined),
        );

        expect(new Set(occupied)).toStrictEqual(new Set(CONTROL_SLOTS));
        expect(faults).toStrictEqual([]);
    });
});

describe("boardGeometry's shell tracks", () => {
    it("stands a 667 x 375 phone's settings target in the right bar, past the right strip", () => {
        const { lengths, tracks } = windowGeometry({ height: 375, width: 667 });
        const areas = slotAreas(tracks);
        const [cornerLeft = 0, , cornerRight = 0] = areas["corner"] ?? [];

        expect(cornerLeft).toBeGreaterThan(areas["strip-right"]?.[2] ?? Number.NaN);
        expect(cornerRight - cornerLeft).toBeGreaterThanOrEqual(lengths["menu-size"] ?? Infinity);
    });

    it("lays a landscape phone's slots where its board measured them", () => {
        expect(slotAreas(windowGeometry({ height: 375, width: 667 }).tracks)).toEqual({
            actions: [144, 233.7, 523, 315.7],
            corner: [623, 4, 663, 375],
            field: [4, 38.9, 90, 177],
            furiten: [4, 185, 90, 203],
            hand: [63.4, 319.7, 609, 369],
            "strip-left": [96, 4, 138, 315.7],
            "strip-right": [529, 4, 571, 315.7],
            "strip-top": [138, 4, 468, 36.3],
            switches: [4, 211, 44, 371],
        });
    });

    it("reserves a phone's own row its standing body's overhang in whole pixels where it runs deeper than the margin, the foot within a pixel of the board's bottom", () => {
        const { lengths } = windowGeometry({ height: 375, width: 667 });
        const [ow = 0, handTop = 0] = [lengths["ow"], lengths["hand-top"]];
        const foot = handTop + STANDING_BODY.height * ow;

        expect(375 - (handTop + (lengths["oh"] ?? 0))).toBe(Math.floor(STANDING_OVERHANG * ow));
        expect(foot - 375).toBeGreaterThanOrEqual(0);
        expect(foot - 375).toBeLessThan(1);
    });

    it("takes a phone's own melds larger than its river tile, at one tile four open kans keep in the row, lifted by what their edge passes the hand's foot", () => {
        const { lengths } = windowGeometry({ height: 375, width: 667 });
        const [ow = 0, meld = 0] = [lengths["ow"], lengths["own-meld-tile"]];
        const row = { cap: meld, gap: lengths["g"] ?? 0, ow, width: lengths["own-row-w"] ?? 0 };
        const openKan = { depth: UPRIGHT_DEPTH, units: 3 + SIDEWAYS_UNITS };

        expect(meld).toBeGreaterThan(lengths["rw"] ?? 0);
        expect(TILE_EDGE_SHARE * meld - (lengths["own-meld-lift"] ?? 0)).toBeLessThanOrEqual(
            Math.floor(STANDING_OVERHANG * ow),
        );
        expect(ownMeldTile(row, [openKan, openKan, openKan, openKan])).toBe(meld);
    });

    it("centres a live phone's panel whatever notices show, reserving them no room beside it", () => {
        const { areas, lengths } = windowGeometry({ height: 393, width: 740 });

        expect(lengths["overlay-left"]).toBe(lengths["overlay-right"]);
        expect(lengths["overlay-right-beside-notices"]).toBeUndefined();
        expect(areas["field-beside"]).toBeUndefined();
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
