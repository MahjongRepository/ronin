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
    LEFT_REACH_TILES,
    OWN_MELD_SCALE,
    PHONE_HEIGHT,
    RIVER_GAP_SHARE,
    SHORT_DESKTOP_HEIGHT,
    SIDE_REACH_TILES,
    SMALL_CHROME_WIDTH,
    TILE_ASPECT,
    TILE_EDGE_SHARE,
} from "./board-constants";

type BoardFamily = "phone" | "desktop" | "short-desktop" | "upright";

interface BoardBox {
    readonly width: number;
    readonly height: number;
}

/** The board's sizes in px, by the stylesheet's length names (`rw` for `--rw`). */
type BoardLengths = Readonly<Record<string, number>>;

interface BoardGeometry {
    readonly family: BoardFamily;
    readonly chrome: ChromeTier;
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

/** What the desktop's river tile is solved from: the board's height, its chrome and the rooms already known. */
interface DesktopRooms {
    readonly height: number;
    readonly tier: DesktopChrome;
    readonly ownFit: number;
    readonly coreCap: number;
    readonly coreRoomW: number;
    readonly rowRiseFixed: number;
}

/** The largest river tile each room both desktops share holds (`_grid.scss`'s `--rw-by-*`), the smallest binding. */
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
    const tiles = 2 * TILE_ASPECT + LEFT_REACH_TILES + OWN_ROW + BAND_TILE_SHARE;
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

/** An opponent's full hand along its line: fourteen tiles, whole-pixel hairlines between them and the drawn tile's gap. */
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

/** The desktop and short desktop's root sizes and what their root solve reads (`_grid.scss`), in px. */
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
        ["g", Math.round(RIVER_GAP_SHARE * rw)],
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
 * The board's geometry from its box: its family and chrome tier, classified as the stylesheet's container queries do,
 * and its sizes in px for the families sized here (the desktop and short desktop's); an empty or non-finite box has no sizes.
 */
function boardGeometry(box: BoardBox): BoardGeometry {
    const family = classifyFamily(box);
    const chrome = classifyChrome(box);
    const sized =
        Number.isFinite(box.width) &&
        Number.isFinite(box.height) &&
        box.width > 0 &&
        box.height > 0;
    const desktop = family === "desktop" || family === "short-desktop";
    const lengths = sized && desktop ? desktopLengths(box, chrome, family) : {};
    return Object.freeze({
        box: Object.freeze({ height: box.height, width: box.width }),
        chrome,
        family,
        lengths: Object.freeze(lengths),
    });
}

export { boardGeometry };
export type { BoardBox, BoardFamily, BoardGeometry, BoardLengths };
