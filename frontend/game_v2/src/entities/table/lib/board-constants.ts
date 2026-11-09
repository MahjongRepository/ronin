import { RIVER_ROWS, RIVER_ROW_SIZE } from "@/entities/tile";

/** A tile's height to its width. */
const TILE_ASPECT = 4 / 3;

/** How deep a laid meld stands, in its tiles' widths: an added kan's stack two tiles, any other meld a tile's height. */
const STACKED_DEPTH = 2;
const UPRIGHT_DEPTH = TILE_ASPECT;

/** How long a sideways or stacked meld tile lies, in tile widths: as long as a tile is tall. */
const SIDEWAYS_UNITS = TILE_ASPECT;

/** A full own hand's width in own tiles: fourteen tiles, the drawn tile's gap and the hairlines between them. */
const FULL_HAND = 14.6;

/** An own meld's tile to the river tile. */
const OWN_MELD_SCALE = 1.2;

/** The gap between the centre and a river, in river tiles. */
const RIVER_GAP_SHARE = 0.3;

/** How far a tile's edge reaches below its box, in shares of its width. */
const TILE_EDGE_SHARE = 0.13;

/** No meld face goes under this width (px). */
const FACE_FLOOR = 13;

/** The least gap between a seat's melds, where their line does not hold them at the face floor otherwise (px). */
const MELD_GAP_TIGHT = 2;

/** A tile's width in hairlines, an opponent's drawn tile's gap in river tiles, and a side lane's clearance (px). */
const TILE_UNITS = 60;
const OPPONENT_DRAWN_GAP = 0.15;
const SIDE_LANE_GAP = 4;

/** An own hand's drawn tile's gap, and its melds' lead past it, in own tiles; the stylesheet's `$drawn-gap` mirrors it. */
const OWN_DRAWN_GAP = 0.35;

/** The gap between a strip's melds past the river gap (px). */
const MELD_GAP_EXTRA = 2;

/** A side strip's drawn gap runs along the light, so it adds the edge it shows and keeps the top strip's clear table. */
const SIDE_DRAWN_GAP = OPPONENT_DRAWN_GAP + TILE_EDGE_SHARE;

/** The core's height past the centre, in river tiles: a gap and a top or bottom river's rows on each side. */
const CORE_TILES = 2 * (RIVER_GAP_SHARE + RIVER_ROWS["run-on"] * TILE_ASPECT);

/** How far a side river's row reaches down from the core's top past its sideways tile, in river tiles. */
const LEFT_REACH_TILES = CORE_TILES / 2 + RIVER_ROW_SIZE - 1;

/** What the side rivers' rows take of the board's width beside the centre, in river tiles. */
const SIDE_REACH_TILES = 2 * RIVER_ROWS.wrap * TILE_ASPECT;

/** A top or bottom river reserves nineteen discards: two rows of six and a third of seven, one sideways. */
const ROWS_BEFORE_RUN_ON = (RIVER_ROWS["run-on"] - 1) * TILE_ASPECT;
const RUN_ON_REACH_TILES = RIVER_ROW_SIZE + TILE_ASPECT;

/** The latest discard's gap from the tile before it and the row above (px), across the light; along it, the geometry
 * adds the tile edge that falls into it. */
const LATEST_DISCARD_GAP = 7;

/** A landscape board under this height is a phone's (px). */
const PHONE_HEIGHT = 520;

/** A landscape board at least `SMALL_CHROME_WIDTH` wide and under this height is a short desktop's (px). */
const SHORT_DESKTOP_HEIGHT = 760;

/** The page's gutter around every board but a phone's (px). */
const PAGE_GUTTER = 10;

/** Chrome is small on a board narrower than this or a phone's height (px). */
const SMALL_CHROME_WIDTH = 1100;

/** Chrome is large on a board at least this wide and tall (px). */
const LARGE_CHROME_WIDTH = 2000;
const LARGE_CHROME_HEIGHT = 1200;

type ChromeTier = "small" | "regular" | "large";

/**
 * A board's chrome px: margins, gaps, the band's control, the own badge, the switches (their chips' size and gap), the
 * counters (the indicator's width, and the padding and rim above and below it), the replay's controls, the opponents'
 * badges and the decisions' least widths.
 */
interface DesktopChrome {
    readonly m: number;
    readonly sep: number;
    readonly coreGap: number;
    readonly controlH: number;
    readonly bandGap: number;
    readonly ownBadgeH: number;
    readonly switchGap: number;
    readonly ownInline: number;
    readonly switchH: number;
    readonly chipGap: number;
    readonly movesH: number;
    readonly countersW: number;
    readonly doraW: number;
    readonly countersFrame: number;
    readonly replayGap: number;
    readonly sideLaneMin: number;
    /** The top badge's least lane: a bot's whole name (`ai-tsumogiri-3`) at the tier's text, off small; a phone's one-line pill also holds its AI mark and riichi stick. */
    readonly topLaneMin: number;
    readonly badgeH: number;
    readonly pillH: number;
    readonly ownPillH: number;
    readonly badgeGap: number;
    readonly sideCardW: number;
    readonly winMinW: number;
    readonly actionMinW: number;
    readonly timerW: number;
    /** The board's and its badges' text size. */
    readonly text: number;
    /** The turn cue's bar under a badge's pill. */
    readonly cueW: number;
    /** The counters' padding at their end and start. */
    readonly doraPadEnd: number;
    readonly doraPadStart: number;
    /** The counters' text size and corner radius. */
    readonly doraText: number;
    readonly doraRadius: number;
    /** The play switches' letter size. */
    readonly switchText: number;
    /** A play switch's width where it shows its whole name; 0 on a tier that shows letters. */
    readonly switchLabelW: number;
    /** A call's word's cap on the river tile height that sets its size. */
    readonly calloutCap: number;
}

const REGULAR_CHROME: DesktopChrome = {
    actionMinW: 96,
    badgeGap: 16,
    badgeH: 54,
    bandGap: 12,
    calloutCap: 40,
    chipGap: 6,
    controlH: 48,
    coreGap: 24,
    countersFrame: 18,
    countersW: 172,
    cueW: 3,
    doraPadEnd: 14,
    doraPadStart: 8,
    doraRadius: 10,
    doraText: 19,
    doraW: 28,
    m: 18,
    movesH: 52,
    ownBadgeH: 40,
    ownInline: 0,
    ownPillH: 38,
    pillH: 50,
    replayGap: 6,
    sep: 40,
    sideCardW: 200,
    sideLaneMin: 125,
    switchGap: 18,
    switchH: 40,
    switchLabelW: 112,
    switchText: 22,
    text: 17,
    timerW: 120,
    topLaneMin: 160,
    winMinW: 150,
};

const DESKTOP_CHROME: Readonly<Record<ChromeTier, DesktopChrome>> = {
    large: {
        ...REGULAR_CHROME,
        badgeGap: 20,
        badgeH: 72,
        calloutCap: 56,
        countersFrame: 22,
        countersW: 223,
        cueW: 4,
        doraPadEnd: 18,
        doraPadStart: 10,
        doraRadius: 14,
        doraText: 26,
        doraW: 37,
        movesH: 60,
        ownBadgeH: 52,
        ownPillH: 52,
        pillH: 70,
        replayGap: 8,
        sideCardW: 270,
        sideLaneMin: 170,
        switchH: 44,
        switchLabelW: 124,
        switchText: 24,
        text: 24,
        timerW: 150,
        topLaneMin: 226,
    },
    regular: REGULAR_CHROME,
    small: {
        ...REGULAR_CHROME,
        actionMinW: 64,
        badgeGap: 8,
        badgeH: 40,
        calloutCap: 20,
        countersFrame: 10,
        countersW: 95,
        doraPadEnd: 6,
        doraPadStart: 4,
        doraRadius: 8,
        doraW: 15,
        movesH: 40,
        ownInline: 96,
        ownPillH: 30,
        pillH: 38,
        replayGap: 4,
        sideCardW: 130,
        sideLaneMin: 90,
        switchGap: 4,
        switchH: 44,
        switchLabelW: 0,
        switchText: 17,
        text: 12,
        timerW: 76,
        topLaneMin: 90,
        winMinW: 96,
    },
};

/** The page's cog: its side, a share of the river tile within a floor and cap. */
const MENU_RIVER_SHARE = 56 / 60;
const MENU_MIN = 40;
const MENU_MAX = 56;

/** The band's control row past its control: the room the decisions' row keeps over it (px). */
const BAND_ROW_EXTRA = 20;

/** Over a panel, a phone's notices stand in a column this wide under the right strip (px). */
const NOTICES_BESIDE_PANEL = 84;

/** The desktop's centre share of the core, and its own tile's and core's caps in shares of the board. */
const DESKTOP_CENTRE_SHARE = 0.33;
const DESKTOP_OWN_CAP_WIDTH = 0.05;
const DESKTOP_OWN_CAP_HEIGHT = 0.1;
const DESKTOP_CORE_CAP = 0.74;

/** Off a phone the own tile is this many river tiles where its caps allow, never under 4/3. */
const OWN_BY_RIVER_OFF_PHONE = 1.6;

/**
 * A phone's own tile: at least this wide (px), at most as wide as a full hand allows clear of both side strips' stacked
 * depth; its centre never under this height, nor under this width (px).
 */
const PHONE_OWN_FLOOR = 36;
const PHONE_CENTRE_MIN_HEIGHT = 68;
const PHONE_CENTRE_MIN_WIDTH = 100;

/** A phone's top badge's one-line pill: its name and marks on one line, so a short centre's right river can rise (px). */
const PHONE_TOP_PILL_H = 24;

/**
 * A phone box too short for the face floor at the own tile's floor (a browser's bars shown) takes the own tile down to
 * the tap floor's width (px, the look spec's 32x42 safety limit) where that lifts the river tile.
 */
const PHONE_OWN_TAP_FLOOR = 32;

/**
 * A phone's chrome over the small tier's, which it keeps as a floor: its margins, gaps and band's control, its switches
 * as tall as it, and its timer.
 */
const PHONE_CHROME: DesktopChrome = {
    ...DESKTOP_CHROME.small,
    bandGap: 8,
    chipGap: 4,
    controlH: 40,
    coreGap: 6,
    m: 4,
    ownInline: 0,
    sep: 6,
    switchH: 40,
    timerW: 60,
    topLaneMin: 155,
};

/** A phone's chrome grows with its river tile past this one (px). */
const PHONE_CHROME_RIVER = 24;

export {
    BAND_ROW_EXTRA,
    CORE_TILES,
    DESKTOP_CENTRE_SHARE,
    DESKTOP_CHROME,
    DESKTOP_CORE_CAP,
    DESKTOP_OWN_CAP_HEIGHT,
    DESKTOP_OWN_CAP_WIDTH,
    FACE_FLOOR,
    FULL_HAND,
    LARGE_CHROME_HEIGHT,
    LARGE_CHROME_WIDTH,
    LATEST_DISCARD_GAP,
    LEFT_REACH_TILES,
    MELD_GAP_EXTRA,
    MELD_GAP_TIGHT,
    MENU_MAX,
    MENU_MIN,
    MENU_RIVER_SHARE,
    NOTICES_BESIDE_PANEL,
    OPPONENT_DRAWN_GAP,
    OWN_BY_RIVER_OFF_PHONE,
    OWN_DRAWN_GAP,
    OWN_MELD_SCALE,
    PAGE_GUTTER,
    PHONE_CENTRE_MIN_HEIGHT,
    PHONE_CENTRE_MIN_WIDTH,
    PHONE_CHROME,
    PHONE_CHROME_RIVER,
    PHONE_HEIGHT,
    PHONE_OWN_FLOOR,
    PHONE_OWN_TAP_FLOOR,
    PHONE_TOP_PILL_H,
    RIVER_GAP_SHARE,
    ROWS_BEFORE_RUN_ON,
    RUN_ON_REACH_TILES,
    SHORT_DESKTOP_HEIGHT,
    SIDE_DRAWN_GAP,
    SIDE_REACH_TILES,
    SIDEWAYS_UNITS,
    SMALL_CHROME_WIDTH,
    STACKED_DEPTH,
    SIDE_LANE_GAP,
    TILE_ASPECT,
    TILE_EDGE_SHARE,
    TILE_UNITS,
    UPRIGHT_DEPTH,
};
export type { ChromeTier, DesktopChrome };
