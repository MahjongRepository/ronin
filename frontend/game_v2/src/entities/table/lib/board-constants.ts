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

/** The px a desktop's sizing reads of its chrome: margins, gaps, the band's control, the own badge and the switches. */
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
}

const REGULAR_CHROME: DesktopChrome = {
    bandGap: 18,
    controlH: 60,
    coreGap: 40,
    m: 18,
    movesH: 52,
    ownBadgeH: 40,
    ownInline: 0,
    sep: 40,
    sideStart: 72,
    switchGap: 18,
    switchH: 44,
};

const DESKTOP_CHROME: Readonly<Record<ChromeTier, DesktopChrome>> = {
    large: {
        ...REGULAR_CHROME,
        movesH: 60,
        ownBadgeH: 52,
        sideStart: 100,
        switchH: 52,
    },
    regular: REGULAR_CHROME,
    small: {
        ...REGULAR_CHROME,
        movesH: 40,
        ownInline: 96,
        sideStart: 52,
        switchGap: 4,
    },
};

/** The desktop's centre share of the core, and its own tile's and core's caps in shares of the board. */
const DESKTOP_CENTRE_SHARE = 0.33;
const DESKTOP_OWN_CAP_WIDTH = 0.05;
const DESKTOP_OWN_CAP_HEIGHT = 0.1;
const DESKTOP_CORE_CAP = 0.66;

/** A phone's centre share of the core, its own tile's cap (px) and its river tile to its own tile. */
const PHONE_CENTRE_SHARE = 0.39;
const PHONE_OWN_CAP = 36;
const RIVER_BY_OWN = 0.65;

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

/** An upright board's chrome over the desktop tier's: a phone's margin, band gap and control, and room before its own hand. */
const UPRIGHT_CHROME = { bandGap: 8, controlH: 40, m: 4, ownInline: 96 } as const;

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
    LEFT_REACH_TILES,
    OWN_MELD_SCALE,
    PAGE_GUTTER,
    PHONE_CENTRE_SHARE,
    PHONE_CHROME,
    PHONE_HEIGHT,
    PHONE_OWN_CAP,
    RIVER_BY_OWN,
    RIVER_GAP_SHARE,
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
