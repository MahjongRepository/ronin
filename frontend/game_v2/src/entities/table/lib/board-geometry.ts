import {
    CENTRE_ASPECT,
    CORE_TILES,
    type ChromeTier,
    DESKTOP_CENTRE_SHARE,
    DESKTOP_CHROME,
    DESKTOP_CORE_CAP,
    DESKTOP_OWN_CAP_HEIGHT,
    DESKTOP_OWN_CAP_WIDTH,
    type DesktopChrome,
    FACE_FLOOR,
    FULL_HAND,
    LARGE_CHROME_HEIGHT,
    LARGE_CHROME_WIDTH,
    LATEST_DISCARD_GAP,
    LEFT_REACH_TILES,
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
    SMALL_CHROME_WIDTH,
    STACKED_DEPTH,
    TILE_ASPECT,
    TILE_EDGE_SHARE,
    UPRIGHT_CHROME,
} from "./board-constants";

type BoardFamily = "phone" | "desktop" | "short-desktop" | "upright";

interface BoardBox {
    readonly width: number;
    readonly height: number;
}

interface BoardEdges {
    readonly top: number;
    readonly right: number;
    readonly bottom: number;
    readonly left: number;
}

/** The board's box as measured, the page's raw safe-area insets and the gutter the page applies (px). */
interface BoardInput {
    readonly box: BoardBox;
    readonly safeInsets: BoardEdges;
    readonly gutter: number;
}

/** The board's sizes in px, by the stylesheet's length names (`rw` for `--rw`). */
type BoardLengths = Readonly<Record<string, number>>;

interface BoardGeometry {
    readonly family: BoardFamily;
    readonly chrome: ChromeTier;
    readonly gutter: number;
    readonly box: BoardBox;
    readonly lengths: BoardLengths;
}

/** The band's control row past its control: the room the decisions' row keeps over it (px). */
const BAND_ROW_EXTRA = 20;

/** What the core's room keeps beside it on a desktop's width, past the margins (px). */
const CORE_ROOM_SIDES = 24;

/** The own badge's lane over the hand's tiles (px). */
const OWN_BADGE_LANE = 2;

/** What the left river's reach and the left hand keep above the switches' place (px). */
const SWITCHES_CLEARANCE = 4;

/** The left hand's full reach ends this far above its room's end (px). */
const LEFT_HAND_GAP = 8;

/** The switches step in this far past an opponent's tile height (px). */
const STEP_IN_GAP = 6;

/** The bottom river keeps this far from the switches' place level with it (px). */
const SWITCHES_RIVER_GAP = 8;

/** The play switches' strip: three square chips and the names' button, and the px between them. */
const SWITCH_CHIPS = 4;
const SWITCHES_GAPS = 18;

/** The replay's moves in the switches' place, and the px between them. */
const REPLAY_MOVES = 7;
const REPLAY_MOVES_GAPS = 36;

/** An opponent's hand: its tiles, a tile's width in hairlines, and its drawn tile's gap in river tiles. */
const HAND_TILES = 14;
const TILE_UNITS = 60;
const OPPONENT_DRAWN_GAP = 0.15;

/** The core's share past the centre, and what each room's height and width hold per river tile. */
const DESKTOP_SPARE = 1 - DESKTOP_CENTRE_SHARE;
const OWN_ROW = TILE_ASPECT * TILE_ASPECT;
const OWN_EDGE = TILE_EDGE_SHARE * TILE_ASPECT;
const BAND_TILE_SHARE = Math.max(0, 2 * Math.min(OWN_MELD_SCALE, TILE_ASPECT) - OWN_ROW);
const HEIGHT_TILES = CORE_TILES + DESKTOP_SPARE * TILE_ASPECT;
const WIDTH_TILES = CORE_TILES + DESKTOP_SPARE * SIDE_REACH_TILES;
const ROWS_AT_MARGIN = HEIGHT_TILES + DESKTOP_SPARE * OWN_ROW;
const ROWS_AT_EDGE = HEIGHT_TILES + DESKTOP_SPARE * (OWN_ROW + OWN_EDGE);

/** The left river's reach under the core's top slot, in river tiles: the slot's tile, the river, its sideways tile. */
const SLOT_LEFT_REACH = 2 * TILE_ASPECT + LEFT_REACH_TILES;

/** A side strip's two stacked lines' gap, and the gap the right hand keeps under the corner (px). */
const STRIP_LINES_GAP = 4;
const CORNER_GAP = 4;

/** The right hand's origin from the band stands this far under the band's top margin (px). */
const RIGHT_FROM_BAND_GAP = 2;

/** A phone's switches' place holds the replay's five moves, 4px apart, wider than the play switches. */
const REPLAY_MOVES_ON_PHONE = 5;
const PLACE_GAP = 4;

/**
 * A phone's side fields beside the deepest strips: the notices' place (7.5 of its 11px ems) and its gaps to the strip
 * and the left river, and the decisions' column (two controls a row) and its gaps (px).
 */
const NOTICE_FIELD = 84;
const NOTICE_GAPS = 14;
const DECISIONS_COLUMN = 84;
const DECISIONS_GAPS = 12;

/**
 * A phone's left badge stands this far past its strip's first line, and keeps at least this lane beside the top
 * river's longest third row, past its clearance of at least `SIDE_CLEAR` (px).
 */
const PHONE_BADGE_GAP = 8;
const PHONE_SIDE_LANE = 90;
const SIDE_CLEAR = 16;

/** No phone's river tile passes this share of its height. */
const PHONE_MAX_RIVER_SHARE = 10;

/** Upright, the counters' place under the top strip: its gap above and its height (px). */
const UPRIGHT_COUNTERS_GAP = 6;
const UPRIGHT_COUNTERS_H = 52;

/**
 * An upright board's notices' place keeps room for one clamped notice (`NOTICE_TAP_MIN`) and the rivers' rounding
 * (px).
 */
const UPRIGHT_NOTICE_ROOM = 44;

/**
 * Upright, the decisions' two rows keep these px between them and the own badge, and the notices this far off the
 * core.
 */
const UPRIGHT_DECISIONS_GAPS = 16;
const UPRIGHT_NOTICE_GAP = 6;

/** A narrow upright board's centre keeps the room its text needs (px). */
const UPRIGHT_CENTRE_MIN = 100;

/**
 * An upright core's height past the centre and what stands under it per river tile: a top strip's depth and the own
 * row.
 */
const UPRIGHT_TILES = CORE_TILES + DESKTOP_SPARE * (STACKED_DEPTH + OWN_ROW + BAND_TILE_SHARE);

function classifyFamily({ width, height }: BoardBox): BoardFamily {
    if (width < height) {
        return "upright";
    }
    if (height < PHONE_HEIGHT) {
        return "phone";
    }
    if (height < SHORT_DESKTOP_HEIGHT && width >= SMALL_CHROME_WIDTH) {
        return "short-desktop";
    }
    return "desktop";
}

function classifyChrome({ width, height }: BoardBox): ChromeTier {
    if (width < SMALL_CHROME_WIDTH || height < PHONE_HEIGHT) {
        return "small";
    }
    if (width >= LARGE_CHROME_WIDTH && height >= LARGE_CHROME_HEIGHT) {
        return "large";
    }
    return "regular";
}

/** What a desktop's or an upright board's river tile is solved from: its height, its chrome and the rooms known. */
interface DesktopRooms {
    readonly height: number;
    readonly tier: DesktopChrome;
    readonly ownFit: number;
    readonly coreCap: number;
    readonly coreRoomW: number;
    readonly rowRiseFixed: number;
}

/** The largest river tile each room the desktops and the upright board share holds, the smallest binding. */
function sharedRiverTile({ coreCap, coreRoomW, height, ownFit, tier }: DesktopRooms): number {
    const { coreGap, m, sep } = tier;
    const heightRoom = DESKTOP_SPARE * (height - m - coreGap - sep);
    return Math.min(
        ownFit / TILE_ASPECT,
        (heightRoom - DESKTOP_SPARE * m) / ROWS_AT_MARGIN,
        heightRoom / ROWS_AT_EDGE,
        (DESKTOP_SPARE * coreCap) / CORE_TILES,
        (DESKTOP_SPARE * coreRoomW) / WIDTH_TILES,
    );
}

/** The largest river tile that keeps the desktop's core above its band. */
function bandRiverTile({ height, rowRiseFixed, tier }: DesktopRooms): number {
    const { bandGap, controlH, m, sep } = tier;
    const bandFixed = sep + bandGap + controlH + BAND_ROW_EXTRA + rowRiseFixed;
    const bandRoom = DESKTOP_SPARE * (height - m - bandFixed);
    const bandRise = DESKTOP_SPARE * BAND_TILE_SHARE;
    return Math.min(
        (bandRoom - DESKTOP_SPARE * m) / (ROWS_AT_MARGIN + bandRise),
        bandRoom / (ROWS_AT_EDGE + bandRise),
    );
}

/**
 * The largest river tile that keeps a short desktop's left river, from the core's top slot, above the switches' place:
 * the slot's river tile, that river's reach, the own row with its meld rise and badge, and the place itself.
 */
function switchesRiverTile({ height, tier }: DesktopRooms): number {
    const { m, ownBadgeH, sep, switchGap } = tier;
    const fixed =
        ownBadgeH + OWN_BADGE_LANE + SWITCHES_CLEARANCE + switchGap + switchesPlace(tier) + sep;
    const tiles = SLOT_LEFT_REACH + OWN_ROW + BAND_TILE_SHARE;
    return Math.min((height - 2 * m - fixed) / tiles, (height - m - fixed) / (tiles + OWN_EDGE));
}

/** The switches' place: as tall and wide as the play switches or the replay's moves, so both boards size alike. */
function switchesPlace({ movesH, switchH }: DesktopChrome): number {
    return Math.max(switchH, movesH);
}

function switchesPlaceWidth({ movesH, switchH }: DesktopChrome): number {
    return Math.max(
        SWITCH_CHIPS * switchH + SWITCHES_GAPS,
        REPLAY_MOVES * movesH + REPLAY_MOVES_GAPS,
    );
}

/**
 * An opponent's full hand along its line: fourteen tiles, whole-pixel hairlines between them and the drawn tile's
 * gap.
 */
function fullReach(rw: number): number {
    const hairline = Math.ceil(rw / TILE_UNITS);
    const drawnGap = Math.round(OPPONENT_DRAWN_GAP * rw);
    return HAND_TILES * rw + (HAND_TILES - 1) * hairline + drawnGap;
}

/** Where the play switches start: stepped in past the left hand where its full reach meets them. */
function switchesLeft(
    tier: DesktopChrome,
    {
        bandTop,
        cy,
        rw,
        switchesTop,
    }: Readonly<Record<"bandTop" | "cy" | "rw" | "switchesTop", number>>,
): number {
    const { m, sideStart } = tier;
    const reach = fullReach(rw);
    const roomEnd = Math.min(bandTop, switchesTop);
    const leftStart = Math.max(
        m + sideStart,
        Math.min(cy - reach / 2, roomEnd - LEFT_HAND_GAP - reach),
    );
    const leftMeets = leftStart + reach + SWITCHES_CLEARANCE > switchesTop;
    return leftMeets ? m + rw * TILE_ASPECT + STEP_IN_GAP : m;
}

/** The gap between the centre and a river, a whole pixel. */
function riverGap(rw: number): number {
    return Math.round(RIVER_GAP_SHARE * rw);
}

/**
 * The rivers' reach at their capacity, a row's sideways riichi tile and the latest discard's gap counted: a side
 * river's fourth row, a top or bottom river's third row run on to twelve tiles, and the top river's third row's
 * centre-facing edge, which no gap moves toward the centre; and the latest discard's gaps.
 */
function riverLengths({
    centre,
    centreWidth,
    cx,
    cy,
    rw,
}: Readonly<Record<"centre" | "centreWidth" | "cx" | "cy" | "rw", number>>): [string, number][] {
    const hx = centreWidth / 2;
    const gap = riverGap(rw);
    const sideReach = (SIDE_REACH_TILES / 2) * rw + LATEST_DISCARD_GAP;
    const runOnReach = RUN_ON_REACH_TILES * rw + LATEST_DISCARD_GAP;
    return [
        ["latest-discard-gap", LATEST_DISCARD_GAP],
        ["reach-bottom-right", cx - hx + runOnReach],
        ["reach-left", cx - hx - gap - sideReach],
        ["reach-right", cx + hx + gap + sideReach],
        ["reach-top-left", cx + hx - runOnReach],
        ["reach-top-row3", cy - centre / 2 - gap - ROWS_BEFORE_RUN_ON * rw],
        ["right-latest-discard-gap", RIGHT_LATEST_DISCARD_GAP],
    ];
}

/** The desktop and short desktop's root sizes and the lengths the stylesheet reads with them, in px. */
function desktopLengths(box: BoardBox, chrome: ChromeTier, family: BoardFamily): BoardLengths {
    const { width, height } = box;
    const short = family === "short-desktop";
    const tier = DESKTOP_CHROME[chrome];
    const { bandGap, controlH, coreGap, m, ownBadgeH, ownInline, sep, switchGap } = tier;
    const ownCap = Math.min(DESKTOP_OWN_CAP_WIDTH * width, DESKTOP_OWN_CAP_HEIGHT * height);
    const ownFit = Math.min(ownCap, (width - 2 * m - ownInline) / FULL_HAND);
    const coreCap = DESKTOP_CORE_CAP * height;
    const coreRoomW = width - 2 * m - CORE_ROOM_SIDES;
    const rowRiseFixed = chrome === "small" ? ownBadgeH + OWN_BADGE_LANE + switchGap - bandGap : 0;
    const rooms = { coreCap, coreRoomW, height, ownFit, rowRiseFixed, tier };
    const familyRiverTile = short ? switchesRiverTile(rooms) : bandRiverTile(rooms);
    const rw = Math.floor(Math.min(sharedRiverTile(rooms), familyRiverTile));
    const rh = rw * TILE_ASPECT;
    const ow = Math.floor(rw * TILE_ASPECT);
    const oh = ow * TILE_ASPECT;

    const handBottom = Math.max(m, ow * TILE_EDGE_SHARE);
    const handTop = height - handBottom - oh;
    const coreRoomH = height - m - handBottom - oh - coreGap - sep;
    const ownMeldTile = Math.max(FACE_FLOOR, Math.min(OWN_MELD_SCALE * rw, ow));
    const ownMeldRise = Math.max(0, 2 * ownMeldTile - oh);
    const bandLift = ownMeldRise;
    const ownRise = ownMeldRise + ownBadgeH + OWN_BADGE_LANE;
    const bandBottom = handTop - bandGap - bandLift;
    const switchesBottom = Math.min(bandBottom, handTop - ownRise - switchGap);
    const rowBottom = chrome === "small" ? switchesBottom : bandBottom;
    const rowRise = bandBottom - rowBottom;
    const bandReserve = bandGap + controlH + BAND_ROW_EXTRA + rowRise + bandLift;
    const coreRoomBand = handTop - bandReserve - m - sep;

    const core = Math.min(
        coreRoomH - rh,
        short ? Infinity : coreRoomBand - rh,
        coreCap,
        coreRoomW - SIDE_REACH_TILES * rw,
    );
    const centre = core - CORE_TILES * rw;
    const coreTopSlot = m + rh + sep;
    const coreTopFree = (coreRoomH - rh - core) / 2;
    const switchesTop = switchesBottom - switchesPlace(tier);
    const coreTopRoom = switchesTop - SWITCHES_CLEARANCE - coreTopSlot - LEFT_REACH_TILES * rw - rh;
    const coreTop = short
        ? coreTopSlot + Math.max(0, Math.min(coreTopFree, coreTopRoom))
        : Math.min(coreTopSlot + coreTopFree, handTop - bandReserve - core);
    const cy = coreTop + core / 2;
    const bandTop = handTop - bandGap - controlH - rowRise - bandLift;
    const centreBySwitches = short
        ? 2 *
          (width / 2 -
              switchesLeft(tier, { bandTop, cy, rw, switchesTop }) -
              switchesPlaceWidth(tier) -
              SWITCHES_RIVER_GAP)
        : Infinity;
    const centreWidth = Math.max(
        centre,
        Math.min(
            centre * CENTRE_ASPECT,
            coreRoomW - (SIDE_REACH_TILES + CORE_TILES) * rw,
            centreBySwitches,
        ),
    );

    return Object.fromEntries([
        ["band-bottom", bandBottom],
        ["band-gap", bandGap],
        ["band-lift", bandLift],
        ...(short ? [] : [["band-reserve", bandReserve]]),
        ["c", centre],
        ["control-h", controlH],
        ["core", core],
        ["core-gap", coreGap],
        ...(short ? [] : [["core-room-band", coreRoomBand]]),
        ["core-room-h", coreRoomH],
        ["core-room-w", coreRoomW],
        ["core-top", coreTop],
        ["cx", width / 2],
        ["cy", cy],
        ["g", riverGap(rw)],
        ["h", centre / 2],
        ["hand-bottom", handBottom],
        ["hand-top", handTop],
        ["hx", centreWidth / 2],
        ["m", m],
        ["oh", oh],
        ["ow", ow],
        ["own-badge-h", ownBadgeH],
        ["own-fit", ownFit],
        ["own-inline", ownInline],
        ["own-meld-rise", ownMeldRise],
        ["own-meld-tile", ownMeldTile],
        ["own-rise", ownRise],
        ...riverLengths({ centre, centreWidth, cx: width / 2, cy, rw }),
        ["rh", rh],
        ["row-rise", rowRise],
        ["rw", rw],
        ["sep", sep],
        ["switch-gap", switchGap],
        ["switches-bottom", switchesBottom],
        ["w", centreWidth],
    ]);
}

/**
 * An upright board's root sizes and the lengths the stylesheet reads with them, in px: its core under the counters and
 * above the decisions' two rows and the notices' place, its centre never under `UPRIGHT_CENTRE_MIN`.
 */
function uprightLengths(box: BoardBox, chrome: ChromeTier): BoardLengths {
    const { width, height } = box;
    const tier = { ...DESKTOP_CHROME[chrome], ...UPRIGHT_CHROME };
    const { bandGap, controlH, coreGap, m, ownBadgeH, ownInline, sep } = tier;
    const ownFit = Math.min(
        DESKTOP_OWN_CAP_HEIGHT * height,
        (width - 2 * m - ownInline) / FULL_HAND,
    );
    const coreCap = DESKTOP_CORE_CAP * height;
    const coreRoomW = width - 2 * m - CORE_ROOM_SIDES;
    const underStrip = m + UPRIGHT_COUNTERS_GAP + UPRIGHT_COUNTERS_H;
    const fixed =
        ownBadgeH +
        2 * controlH +
        UPRIGHT_DECISIONS_GAPS +
        OWN_BADGE_LANE +
        UPRIGHT_NOTICE_GAP +
        UPRIGHT_NOTICE_ROOM +
        underStrip;
    const edgeTiles = UPRIGHT_TILES + DESKTOP_SPARE * OWN_EDGE;
    const rw = Math.floor(
        Math.min(
            sharedRiverTile({
                coreCap,
                coreRoomW,
                height,
                ownFit,
                rowRiseFixed: 0,
                tier,
            }),
            (DESKTOP_SPARE * (height - m - fixed)) / UPRIGHT_TILES,
            (DESKTOP_SPARE * (height - fixed)) / edgeTiles,
            (coreRoomW - UPRIGHT_CENTRE_MIN) / (CORE_TILES + SIDE_REACH_TILES),
        ),
    );
    const rh = rw * TILE_ASPECT;
    const ow = Math.floor(rw * TILE_ASPECT);
    const oh = ow * TILE_ASPECT;

    const handBottom = Math.max(m, ow * TILE_EDGE_SHARE);
    const handTop = height - handBottom - oh;
    const coreRoomH = height - m - handBottom - oh - coreGap - sep;
    const ownMeldTile = Math.max(FACE_FLOOR, Math.min(OWN_MELD_SCALE * rw, ow));
    const ownMeldRise = Math.max(0, 2 * ownMeldTile - oh);
    const ownRise = ownMeldRise + ownBadgeH + OWN_BADGE_LANE;
    const noticesBottom = handTop - ownRise - 2 * controlH - UPRIGHT_DECISIONS_GAPS;
    const bandReserve = handTop - noticesBottom + UPRIGHT_NOTICE_ROOM + UPRIGHT_NOTICE_GAP;
    const coreRoomBand = handTop - bandReserve - underStrip;
    const stripDepth = STACKED_DEPTH * rw;

    const core = Math.min(
        coreRoomH - rh,
        coreRoomBand - stripDepth,
        coreCap,
        coreRoomW - SIDE_REACH_TILES * rw,
    );
    const centre = core - CORE_TILES * rw;
    const centreWidth = Math.max(
        centre,
        Math.min(centre * CENTRE_ASPECT, coreRoomW - (SIDE_REACH_TILES + CORE_TILES) * rw),
    );
    const coreFloor = underStrip + stripDepth;
    const coreTopSlot = m + rh + sep;
    const coreTopFree = (coreRoomH - rh - core) / 2;
    const coreTop = Math.max(
        coreFloor,
        Math.min(coreTopSlot + coreTopFree, handTop - bandReserve - core),
    );
    const cy = coreTop + core / 2;

    return Object.fromEntries([
        ["band-gap", bandGap],
        ["band-reserve", bandReserve],
        ["c", centre],
        ["control-h", controlH],
        ["core", core],
        ["core-floor", coreFloor],
        ["core-gap", coreGap],
        ["core-room-band", coreRoomBand],
        ["core-room-h", coreRoomH],
        ["core-room-w", coreRoomW],
        ["core-top", coreTop],
        ["cx", width / 2],
        ["cy", cy],
        ["g", riverGap(rw)],
        ["h", centre / 2],
        ["hand-bottom", handBottom],
        ["hand-top", handTop],
        ["hx", centreWidth / 2],
        ["m", m],
        ["notices-bottom", noticesBottom],
        ["oh", oh],
        ["ow", ow],
        ["own-badge-h", ownBadgeH],
        ["own-fit", ownFit],
        ["own-inline", ownInline],
        ["own-meld-rise", ownMeldRise],
        ["own-meld-tile", ownMeldTile],
        ["own-rise", ownRise],
        ...riverLengths({ centre, centreWidth, cx: width / 2, cy, rw }),
        ["rh", rh],
        ["rw", rw],
        ["sep", sep],
        ["w", centreWidth],
    ]);
}

/** A phone's chrome lengths, by the stylesheet's names. */
type PhoneChrome = Readonly<
    Record<
        keyof typeof PHONE_DRAWN_CHROME | "control-h" | "moves-h" | "own-badge-h" | "switch-h",
        number
    >
>;

/** The deepest a side strip reaches: two stacked lines 4px apart, the second's tiles never under the face floor. */
function stripReserve(rw: number): number {
    return STACKED_DEPTH * rw + STRIP_LINES_GAP + STACKED_DEPTH * Math.max(rw, FACE_FLOOR);
}

/** A phone's chrome at its river tile: the small tier's px, growing with the river tile past `PHONE_CHROME_RIVER`. */
function phoneChrome(rw: number): PhoneChrome {
    const scale = Math.max(1, rw / PHONE_CHROME_RIVER);
    const control = PHONE_CHROME.controlH * scale;
    const drawn = Object.fromEntries(
        Object.entries(PHONE_DRAWN_CHROME).map(([name, px]) => [name, px * scale]),
    ) as Record<keyof typeof PHONE_DRAWN_CHROME, number>;
    return {
        ...drawn,
        "control-h": control,
        "moves-h": control,
        "own-badge-h": PHONE_CHROME.ownBadgeH * scale,
        "switch-h": control,
    };
}

/**
 * Where a phone's right hand runs, from its full reach: centred under the corner above the band, else up to the top
 * margin above it, else from under the corner across the band, else from the top margin across it, short of the own
 * row; the corner, the band's row or both stepping in past it. `null` where even that enters the own row.
 */
function phoneRightHand({
    bandTop,
    cornerBottom,
    cy,
    fromBand,
    ownRowTop,
    reach,
}: Readonly<
    Record<"bandTop" | "cornerBottom" | "cy" | "fromBand" | "ownRowTop" | "reach", number>
>): {
    readonly origin: number;
    readonly cornerIn: boolean;
    readonly bandCrossed: boolean;
} | null {
    const { m } = PHONE_CHROME;
    const underCorner = Math.max(fromBand, cornerBottom + CORNER_GAP + reach);
    const fromTop = Math.max(fromBand, m + reach);
    const centred = Math.max(cornerBottom + CORNER_GAP + reach, cy + reach / 2);
    if (underCorner <= bandTop) {
        return {
            bandCrossed: false,
            cornerIn: false,
            origin: Math.min(underCorner, centred),
        };
    }
    if (fromTop <= bandTop) {
        return {
            bandCrossed: false,
            cornerIn: true,
            origin: Math.min(fromTop, centred),
        };
    }
    if (underCorner <= ownRowTop) {
        return {
            bandCrossed: true,
            cornerIn: false,
            origin: Math.min(underCorner, centred),
        };
    }
    return fromTop <= ownRowTop ? { bandCrossed: true, cornerIn: true, origin: fromTop } : null;
}

/** A phone's lengths at a river and own tile, in px, or `null` where its places do not fit them. */
function phoneLayout({ width, height }: BoardBox, rw: number, ow: number): BoardLengths | null {
    const { bandGap, coreGap, m, sep, sideStart, switchGap } = PHONE_CHROME;
    const chrome = phoneChrome(rw);
    const { "control-h": controlH, "corner-h": cornerH, "own-badge-h": ownBadgeH } = chrome;
    const rh = rw * TILE_ASPECT;
    const oh = ow * TILE_ASPECT;
    const handBottom = Math.max(m, ow * TILE_EDGE_SHARE);
    const handTop = height - handBottom - oh;
    const ownMeldTile = Math.max(FACE_FLOOR, Math.min(OWN_MELD_SCALE * rw, ow));
    const ownMeldRise = Math.max(0, 2 * ownMeldTile - oh);
    const ownRise = ownMeldRise + ownBadgeH + OWN_BADGE_LANE;
    const bandBottom = handTop - bandGap;
    const switchesBottom = Math.min(bandBottom, handTop - ownRise - switchGap);
    const switchesTop = switchesBottom - controlH;
    const coreTop = m + rh + sep;
    const rows = riverGap(rw) + (CORE_TILES / 2 - RIVER_GAP_SHARE) * rw;
    const centreTop = coreTop + LATEST_DISCARD_GAP + rows;
    const heightRoom = handTop - coreGap - LATEST_DISCARD_GAP - rows - centreTop;
    const sideReach = riverGap(rw) + (SIDE_REACH_TILES / 2) * rw + LATEST_DISCARD_GAP;
    const fieldHalf = width / 2 - sideReach - m - stripReserve(rw);
    const runOnReach = RUN_ON_REACH_TILES * rw + LATEST_DISCARD_GAP;
    const leftBadgeX = m + STACKED_DEPTH * rw + PHONE_BADGE_GAP;
    const laneHalf =
        PHONE_SIDE_LANE + Math.max(SIDE_CLEAR, rw) + leftBadgeX + runOnReach - width / 2;
    const centreMin = Math.max(
        PHONE_CENTRE_MIN,
        (DESKTOP_CENTRE_SHARE / DESKTOP_SPARE) * CORE_TILES * rw,
    );
    const switchesRight =
        m +
        STACKED_DEPTH * rw +
        STEP_IN_GAP +
        REPLAY_MOVES_ON_PHONE * controlH +
        (REPLAY_MOVES_ON_PHONE - 1) * PLACE_GAP;
    const clearHalf = width / 2 - sideReach - SWITCHES_CLEARANCE - switchesRight;
    const besideSwitches = clearHalf >= Math.max(centreMin / 2, laneHalf);
    const halfRoom = Math.min(
        fieldHalf - NOTICE_FIELD - NOTICE_GAPS,
        fieldHalf - DECISIONS_COLUMN - DECISIONS_GAPS,
        besideSwitches ? clearHalf : Infinity,
    );
    const centre = Math.min(heightRoom, 2 * halfRoom);
    const centreWidth = Math.max(
        centre,
        2 * laneHalf,
        Math.min(centre * CENTRE_ASPECT, 2 * halfRoom),
    );
    const leftRiverEnd = coreTop + LATEST_DISCARD_GAP + LEFT_REACH_TILES * rw + rh;
    const reach = fullReach(rw);
    const cy = centreTop + centre / 2;
    const cornerBottom = m + cornerH;
    const right = phoneRightHand({
        bandTop: handTop - bandGap - controlH,
        cornerBottom,
        cy,
        fromBand: handTop - 2 * bandGap - controlH + RIGHT_FROM_BAND_GAP,
        ownRowTop: handTop - ownMeldRise - SWITCHES_CLEARANCE,
        reach,
    });
    const fits =
        centre >= centreMin &&
        laneHalf <= halfRoom &&
        leftRiverEnd + SWITCHES_CLEARANCE <= (besideSwitches ? handTop - ownRise : switchesTop) &&
        m + sideStart + reach <= height - m &&
        right !== null;
    if (!fits) {
        return null;
    }
    const stepIn = rh + STEP_IN_GAP;

    return Object.fromEntries([
        ...Object.entries(chrome),
        ["band-bottom", bandBottom],
        ["band-gap", bandGap],
        ["band-lift", 0],
        ["band-shift", right.bandCrossed ? stepIn : 0],
        ["c", centre],
        ["core", 2 * (LATEST_DISCARD_GAP + rows) + centre],
        ["core-gap", coreGap],
        ["core-room-h", height - m - handBottom - oh - coreGap - sep],
        ["core-room-w", width - 2 * m - CORE_ROOM_SIDES],
        ["core-top", coreTop],
        ["corner-in", right.cornerIn ? 1 : 0],
        ["corner-shift", right.cornerIn ? stepIn : 0],
        ["cx", width / 2],
        ["cy", cy],
        ["g", riverGap(rw)],
        ["h", centre / 2],
        ["hand-bottom", handBottom],
        ["hand-top", handTop],
        ["hx", centreWidth / 2],
        ["m", m],
        ["oh", oh],
        ["ow", ow],
        ["own-fit", ow],
        ["own-inline", 0],
        ["own-meld-rise", ownMeldRise],
        ["own-meld-tile", ownMeldTile],
        ["own-rise", ownRise],
        ...riverLengths({ centre, centreWidth, cx: width / 2, cy, rw }),
        ["rh", rh],
        ["right-origin", right.origin],
        ["row-rise", 0],
        ["rw", rw],
        ["sep", sep],
        ["switch-gap", switchGap],
        ["switches-bottom", switchesBottom],
        ["w", centreWidth],
    ]);
}

/**
 * A phone's root sizes and the lengths the stylesheet reads with them, in px: the largest river tile that fits, then
 * the largest own tile that fits with it, at most `OWN_BY_RIVER_MAX` river tiles but never under `PHONE_OWN_FLOOR`,
 * which wins where both cannot hold.
 */
function phoneLengths(box: BoardBox): BoardLengths {
    const ownFit = Math.floor((box.width - 2 * PHONE_CHROME.m) / FULL_HAND);
    for (let rw = Math.floor(box.height / PHONE_MAX_RIVER_SHARE); rw > 1; rw -= 1) {
        const largest = Math.max(
            PHONE_OWN_FLOOR,
            Math.min(Math.floor(OWN_BY_RIVER_MAX * rw), ownFit),
        );
        for (let ow = largest; ow >= PHONE_OWN_FLOOR; ow -= 1) {
            const layout = phoneLayout(box, rw, ow);
            if (layout !== null) {
                return layout;
            }
        }
    }
    return {};
}

function familyLengths(box: BoardBox, chrome: ChromeTier, family: BoardFamily): BoardLengths {
    if (family === "phone") {
        return phoneLengths(box);
    }
    if (family === "upright") {
        return uprightLengths(box, chrome);
    }
    return desktopLengths(box, chrome, family);
}

/** What a gutter adds to an edge beyond its safe inset. */
function gutterExcess(inset: number, gutter: number): number {
    return Math.max(inset, gutter) - inset;
}

/** The board's box with each edge's excess under the applied gutter taken back and its excess under `to` taken off. */
function reguttered({ box, gutter, safeInsets }: BoardInput, to: number): BoardBox {
    function change(inset: number): number {
        return gutterExcess(inset, gutter) - gutterExcess(inset, to);
    }
    const { bottom, left, right, top } = safeInsets;
    return {
        height: box.height + change(top) + change(bottom),
        width: box.width + change(left) + change(right),
    };
}

/**
 * The board's geometry: the candidate box (its allocation without a gutter, less a gutter's excess) classified once,
 * a phone taking no gutter and the allocation, any other family the gutter and the candidate box, and its sizes in px
 * for that box; an empty or non-finite box has no sizes.
 */
function boardGeometry(input: BoardInput): BoardGeometry {
    const candidate = reguttered(input, PAGE_GUTTER);
    const family = classifyFamily(candidate);
    const chrome = classifyChrome(candidate);
    const phone = family === "phone";
    const settled = phone ? reguttered(input, 0) : candidate;
    const sized =
        Number.isFinite(settled.width) &&
        Number.isFinite(settled.height) &&
        settled.width > 0 &&
        settled.height > 0;
    const lengths = sized ? familyLengths(settled, chrome, family) : {};
    return Object.freeze({
        box: Object.freeze(settled),
        chrome,
        family,
        gutter: phone ? 0 : PAGE_GUTTER,
        lengths: Object.freeze(lengths),
    });
}

export { boardGeometry };
export type { BoardBox, BoardEdges, BoardFamily, BoardGeometry, BoardInput, BoardLengths };
