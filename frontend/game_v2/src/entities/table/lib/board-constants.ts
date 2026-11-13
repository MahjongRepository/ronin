import { LYING_BODY, RIVER_ROWS } from "@/entities/tile";

/** A tile's height to its width. */
const TILE_ASPECT = 4 / 3;

/** How deep a laid meld stands, in its tiles' widths: an added kan's stack two tiles, any other meld a tile's height. */
const STACKED_DEPTH = 2;
const UPRIGHT_DEPTH = TILE_ASPECT;

/** The top strip's melds keep this far above the core (px). */
const TOP_CORE_CLEAR = 8;

/** How long a sideways or stacked meld tile lies, in tile widths: as long as a tile is tall. */
const SIDEWAYS_UNITS = TILE_ASPECT;

/** A full own hand's width in own tiles: fourteen tiles, the drawn tile's gap and the hairlines between them. */
const FULL_HAND = 14.6;

/** An own meld's tile to the river tile. */
const OWN_MELD_SCALE = 1;
const OWN_LYING_HEIGHT_SHARE = LYING_BODY.ownTopShare;

/** The gap between the centre and a river, in river tiles. */
const RIVER_GAP_SHARE = 0.3;

/** How far a tile's edge reaches below its box, in shares of its width. */
const TILE_EDGE_SHARE = LYING_BODY.edge;
const OWN_LYING_EDGE_SHARE = LYING_BODY.ownEdge;

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

/** What the side rivers' rows take of the board's width beside the centre, in river tiles. */
const SIDE_REACH_TILES = 2 * RIVER_ROWS.wrap * TILE_ASPECT;

/** A top or bottom river reserves twenty discards: two rows of six and a third of eight, one sideways. */
const RESERVED_THIRD_ROW = 8;
const ROWS_BEFORE_RUN_ON = (RIVER_ROWS["run-on"] - 1) * TILE_ASPECT;
const RUN_ON_REACH_TILES = RESERVED_THIRD_ROW - 1 + TILE_ASPECT;

/** The latest discard's gap from the tile before it and the row above (px), across the light; along it, the geometry
 * adds the tile edge that falls into it. */
const LATEST_DISCARD_GAP = 7;

/** A landscape board under this height is a phone's (px). */
const PHONE_HEIGHT = 520;

/** A desktop board's chrome grows past the regular record only from this height (px). */
const REGULAR_CHROME_HEIGHT = 760;

/** A phone's table column, which the opponents' side strips stand at the edges of, is at least this many river tiles wide. */
const TABLE_COLUMN_TILES = 25;

/** The least bar beside the table column on each side (px). */
const BAR_MIN = 96;

/** The page's gutter around every board but a phone's (px). */
const PAGE_GUTTER = 10;

/** Chrome is small on a board narrower than this or a phone's height (px). */
const SMALL_CHROME_WIDTH = 1100;

/** Chrome is large on a board at least this wide and tall (px). */
const LARGE_CHROME_WIDTH = 2000;
const LARGE_CHROME_HEIGHT = 1200;

type ChromeTier = "small" | "regular" | "large";

/**
 * A board's chrome px: the decisions' least control, the switches (their chips' size and gap), the replay's controls,
 * the opponents' badges and the decisions' least widths.
 */
interface TierChrome {
    readonly controlH: number;
    readonly switchH: number;
    readonly chipGap: number;
    readonly movesH: number;
    readonly replayGap: number;
    /** A plate's one-line pill, every seat's alike. */
    readonly pillH: number;
    readonly actionMinW: number;
    readonly timerW: number;
    /** The board's and its badges' text size. */
    readonly text: number;
    /** The turn cue's bar under a badge's pill. */
    readonly cueW: number;
    /** The play switches' letter size. */
    readonly switchText: number;
    /** A play switch's width where it shows its whole name; 0 on a tier that shows letters. */
    readonly switchLabelW: number;
    /** A call's word's cap on the river tile height that sets its size. */
    readonly calloutCap: number;
}

const REGULAR_CHROME: TierChrome = {
    actionMinW: 96,
    calloutCap: 40,
    chipGap: 6,
    controlH: 48,
    cueW: 3,
    movesH: 52,
    pillH: 30,
    replayGap: 6,
    switchH: 40,
    switchLabelW: 112,
    switchText: 22,
    text: 17,
    timerW: 120,
};

const TIER_CHROME: Readonly<Record<ChromeTier, TierChrome>> = {
    large: {
        ...REGULAR_CHROME,
        calloutCap: 56,
        cueW: 4,
        movesH: 60,
        pillH: 42,
        replayGap: 8,
        switchH: 44,
        switchLabelW: 124,
        switchText: 24,
        text: 24,
        timerW: 150,
    },
    regular: REGULAR_CHROME,
    small: {
        ...REGULAR_CHROME,
        actionMinW: 64,
        calloutCap: 20,
        movesH: 40,
        pillH: 24,
        replayGap: 4,
        switchH: 44,
        switchLabelW: 0,
        switchText: 17,
        text: 12,
        timerW: 76,
    },
};

/** The page's cog: its side, a share of the river tile within a floor and cap. */
const MENU_RIVER_SHARE = 56 / 60;
const MENU_MIN = 40;
const MENU_MAX = 56;

/**
 * Off a phone the own tile is at most this many river tiles (floored to a pixel), so the own hand reads as the table's
 * largest; the bars give up their named switches and the counters' row before it goes under the wanted share, and it
 * never goes under the least, which a window whose width binds its river tile reaches, its side felt down to the side
 * rivers' fourth rows' reserve.
 */
const OWN_BY_RIVER_OFF_PHONE = 1.45;
const OWN_BY_RIVER_WANTED = 1.3;
const OWN_BY_RIVER_LEAST = 1.2;

/** Off a phone the centre is this many river tiles tall, the side rivers' rows running on past it into the corners. */
const DESKTOP_CENTRE_TILES = 4.5;

/** Off a phone the gap between the centre and a river, in river tiles. */
const DESKTOP_RIVER_GAP_SHARE = 0.15;

/**
 * A desktop's vertical stack's gaps, in river tiles: under the top hand's tile edge to the top river's reserved third
 * row, and from the bottom river's reserved third row to the own melds' rise.
 */
const TOP_HAND_GAP = 0.1;
const OWN_ROW_GAP = 0.2;

/** A width-bound desktop's table stands this many river tiles taller than its stack needs, the air under the top hand. */
const TOP_HAND_AIR = 0.3;

/**
 * A phone's own tile: at least this wide (px), at most as wide as a full hand allows clear of both side strips' stacked
 * depth; its centre never under this height, nor under this width (px).
 */
const PHONE_OWN_FLOOR = 36;
const PHONE_CENTRE_MIN_HEIGHT = 68;
const PHONE_CENTRE_MIN_WIDTH = 100;

/**
 * A phone box too short for the face floor at the own tile's floor (a browser's bars shown) takes the own tile down to
 * the tap floor's width (px, the look spec's 32x42 safety limit) where that lifts the river tile.
 */
const PHONE_OWN_TAP_FLOOR = 32;
const PHONE_OWN_GIVEN_FOR_RIVER = 2;

/**
 * A phone's chrome past a desktop's: its margin, the gaps under the top strip and over the own row, and its counters'
 * dora tile where its left bar holds it.
 */
interface PhoneChrome extends TierChrome {
    readonly doraW: number;
    readonly m: number;
    readonly sep: number;
    readonly coreGap: number;
}

/**
 * A phone's chrome over the small tier's, which it keeps as a floor: its margins, gaps and control, its switches as tall
 * as it, and its timer.
 */
const PHONE_CHROME: PhoneChrome = {
    ...TIER_CHROME.small,
    chipGap: 4,
    controlH: 40,
    coreGap: 6,
    doraW: 15,
    m: 4,
    sep: 6,
    switchH: 40,
    timerW: 60,
};

/** A phone's chrome grows with its river tile past this one (px). */
const PHONE_CHROME_RIVER = 24;

export {
    BAR_MIN,
    CORE_TILES,
    DESKTOP_CENTRE_TILES,
    DESKTOP_RIVER_GAP_SHARE,
    FACE_FLOOR,
    FULL_HAND,
    LARGE_CHROME_HEIGHT,
    LARGE_CHROME_WIDTH,
    LATEST_DISCARD_GAP,
    MELD_GAP_EXTRA,
    MELD_GAP_TIGHT,
    MENU_MAX,
    MENU_MIN,
    MENU_RIVER_SHARE,
    OPPONENT_DRAWN_GAP,
    OWN_BY_RIVER_LEAST,
    OWN_BY_RIVER_OFF_PHONE,
    OWN_BY_RIVER_WANTED,
    OWN_DRAWN_GAP,
    OWN_LYING_EDGE_SHARE,
    OWN_LYING_HEIGHT_SHARE,
    OWN_MELD_SCALE,
    OWN_ROW_GAP,
    PAGE_GUTTER,
    PHONE_CENTRE_MIN_HEIGHT,
    PHONE_CENTRE_MIN_WIDTH,
    PHONE_CHROME,
    PHONE_CHROME_RIVER,
    PHONE_HEIGHT,
    PHONE_OWN_FLOOR,
    PHONE_OWN_GIVEN_FOR_RIVER,
    PHONE_OWN_TAP_FLOOR,
    REGULAR_CHROME_HEIGHT,
    RIVER_GAP_SHARE,
    ROWS_BEFORE_RUN_ON,
    RUN_ON_REACH_TILES,
    SIDEWAYS_UNITS,
    SIDE_DRAWN_GAP,
    SIDE_LANE_GAP,
    SIDE_REACH_TILES,
    SMALL_CHROME_WIDTH,
    STACKED_DEPTH,
    TOP_CORE_CLEAR,
    TABLE_COLUMN_TILES,
    TIER_CHROME,
    TILE_ASPECT,
    TILE_EDGE_SHARE,
    TILE_UNITS,
    TOP_HAND_AIR,
    TOP_HAND_GAP,
    UPRIGHT_DEPTH,
};
export type { ChromeTier, PhoneChrome, TierChrome };
