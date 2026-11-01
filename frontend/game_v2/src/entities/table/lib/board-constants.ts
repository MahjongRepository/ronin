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

/** The centre's width to its height where the board's width allows. */
const CENTRE_ASPECT = 1.4;

/** How far a tile's edge reaches below its box, in shares of its width. */
const TILE_EDGE_SHARE = 0.13;

/** No meld face goes under this width (px). */
const FACE_FLOOR = 13;

/** The core's height past the centre, in river tiles: a gap and a top or bottom river's rows on each side. */
const CORE_TILES = 2 * (RIVER_GAP_SHARE + RIVER_ROWS["run-on"] * TILE_ASPECT);

/** How far a side river's row reaches down from the core's top past its sideways tile, in river tiles. */
const LEFT_REACH_TILES = CORE_TILES / 2 + RIVER_ROW_SIZE - 1;

/** What the side rivers' rows take of the board's width beside the centre, in river tiles. */
const SIDE_REACH_TILES = 2 * RIVER_ROWS.wrap * TILE_ASPECT;

/** A top or bottom river's rows before its third, in river tiles; the third runs on to twelve tiles, one sideways. */
const ROWS_BEFORE_RUN_ON = (RIVER_ROWS["run-on"] - 1) * TILE_ASPECT;
const RUN_ON_REACH_TILES = 2 * RIVER_ROW_SIZE - 1 + TILE_ASPECT;

/** The latest discard's gap from the tile before it and the row above (px); the right river's runs up the screen. */
const LATEST_DISCARD_GAP = 7;
const RIGHT_LATEST_DISCARD_GAP = 10;

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
 * The px a desktop's sizing and places read of its chrome: margins, gaps, the band's control, the own badge, the
 * switches, the corner, the replay's controls, the opponents' badges and the decisions' least widths; the stylesheet's
 * chrome blocks mirror the badges' and the decisions'.
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
    readonly movesH: number;
    readonly sideStart: number;
    readonly cornerH: number;
    readonly replayGap: number;
    readonly sideLaneMin: number;
    readonly badgeH: number;
    readonly pillH: number;
    readonly badgeGap: number;
    readonly sideCardW: number;
    readonly winMinW: number;
    readonly actionMinW: number;
    readonly timerW: number;
}

const REGULAR_CHROME: DesktopChrome = {
    actionMinW: 96,
    badgeGap: 16,
    badgeH: 54,
    bandGap: 18,
    controlH: 60,
    coreGap: 40,
    cornerH: 48,
    m: 18,
    movesH: 52,
    ownBadgeH: 40,
    ownInline: 0,
    pillH: 50,
    replayGap: 6,
    sep: 40,
    sideCardW: 200,
    sideLaneMin: 125,
    sideStart: 72,
    switchGap: 18,
    switchH: 44,
    timerW: 120,
    winMinW: 150,
};

const DESKTOP_CHROME: Readonly<Record<ChromeTier, DesktopChrome>> = {
    large: {
        ...REGULAR_CHROME,
        badgeGap: 20,
        badgeH: 72,
        cornerH: 64,
        movesH: 60,
        ownBadgeH: 52,
        pillH: 70,
        replayGap: 8,
        sideCardW: 270,
        sideLaneMin: 170,
        sideStart: 100,
        switchH: 52,
        timerW: 150,
    },
    regular: REGULAR_CHROME,
    small: {
        ...REGULAR_CHROME,
        actionMinW: 64,
        badgeGap: 8,
        badgeH: 40,
        cornerH: 40,
        movesH: 40,
        ownInline: 96,
        pillH: 38,
        replayGap: 4,
        sideCardW: 130,
        sideLaneMin: 90,
        sideStart: 52,
        switchGap: 4,
        timerW: 76,
        winMinW: 96,
    },
};

/** The page's cog: its side at this share of the river tile within its floor and cap, and the room kept past it. */
const MENU_RIVER_SHARE = 56 / 60;
const MENU_MIN = 40;
const MENU_MAX = 56;
const MENU_GAP = 6;

/** Over a panel, a phone's or an upright board's notices stand in a column this wide under the right strip (px). */
const NOTICES_BESIDE_PANEL = 84;

/** The desktop's centre share of the core, and its own tile's and core's caps in shares of the board. */
const DESKTOP_CENTRE_SHARE = 0.33;
const DESKTOP_OWN_CAP_WIDTH = 0.05;
const DESKTOP_OWN_CAP_HEIGHT = 0.1;
const DESKTOP_CORE_CAP = 0.66;

/**
 * A phone's own tile: at least this wide (px) and at most this many river tiles where the floor allows; its centre
 * never under this height (px).
 */
const PHONE_OWN_FLOOR = 36;
const OWN_BY_RIVER_MAX = 1.7;
const PHONE_CENTRE_MIN = 94;

/** A phone's chrome over the small tier's: its margins, gaps and band's control, its switches as tall as it. */
const PHONE_CHROME: DesktopChrome = {
    ...DESKTOP_CHROME.small,
    bandGap: 8,
    controlH: 40,
    coreGap: 6,
    m: 4,
    ownInline: 0,
    sep: 10,
    switchH: 40,
};

/** A phone's drawn chrome at the small tier's px (the stylesheet's small-chrome block), which it keeps as a floor. */
const PHONE_DRAWN_CHROME = {
    "badge-h": 40,
    "corner-h": 40,
    "counters-w": 95,
    "dora-w": 15,
    "own-pill-h": 30,
    "pill-h": 38,
    "timer-w": 60,
} as const;

/** A phone's chrome grows with its river tile past this one (px). */
const PHONE_CHROME_RIVER = 24;

/** An upright board's chrome over the desktop tier's: a phone's margin, band gap and control, and room before its own hand. */
const UPRIGHT_CHROME = {
    bandGap: 8,
    controlH: 40,
    m: 4,
    ownInline: 96,
} as const;

export {
    CENTRE_ASPECT,
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
    MENU_GAP,
    MENU_MAX,
    MENU_MIN,
    MENU_RIVER_SHARE,
    NOTICES_BESIDE_PANEL,
    OWN_BY_RIVER_MAX,
    OWN_MELD_SCALE,
    PAGE_GUTTER,
    PHONE_CENTRE_MIN,
    PHONE_CHROME,
    PHONE_CHROME_RIVER,
    PHONE_DRAWN_CHROME,
    PHONE_HEIGHT,
    PHONE_OWN_FLOOR,
    RIGHT_LATEST_DISCARD_GAP,
    RIVER_GAP_SHARE,
    ROWS_BEFORE_RUN_ON,
    RUN_ON_REACH_TILES,
    SHORT_DESKTOP_HEIGHT,
    SIDE_REACH_TILES,
    SIDEWAYS_UNITS,
    SMALL_CHROME_WIDTH,
    STACKED_DEPTH,
    TILE_ASPECT,
    TILE_EDGE_SHARE,
    UPRIGHT_CHROME,
    UPRIGHT_DEPTH,
};
export type { ChromeTier, DesktopChrome };
