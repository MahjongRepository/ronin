import { RIVER_ROWS, RIVER_ROW_SIZE } from "@/entities/tile";

import {
    BAND_ROW_EXTRA,
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
    MELD_GAP_EXTRA,
    MENU_MAX,
    MENU_MIN,
    MENU_RIVER_SHARE,
    NOTICES_BESIDE_PANEL,
    OWN_BY_RIVER_OFF_PHONE,
    OWN_MELD_SCALE,
    PAGE_GUTTER,
    PHONE_CENTRE_MIN,
    PHONE_CHROME,
    PHONE_CHROME_RIVER,
    PHONE_HEIGHT,
    PHONE_OWN_FLOOR,
    RIVER_GAP_SHARE,
    ROWS_BEFORE_RUN_ON,
    RUN_ON_REACH_TILES,
    SHORT_DESKTOP_HEIGHT,
    SIDEWAYS_UNITS,
    SIDE_LANE_GAP,
    SIDE_REACH_TILES,
    SMALL_CHROME_WIDTH,
    STACKED_DEPTH,
    TILE_ASPECT,
    TILE_EDGE_SHARE,
    UPRIGHT_CHROME,
    UPRIGHT_DEPTH,
    UPRIGHT_NOTICE_GAP,
    UPRIGHT_NOTICE_ROOM,
} from "./board-constants";
import {
    type StripObstacle,
    type StripRooms,
    type StripSeat,
    drawnGap,
    hairline,
    handLength,
} from "./strip-layout";

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

/** The slots the board's page fills: whose controls hold the band (live play's or a replay's). */
interface BoardSlots {
    readonly band: "play" | "replay";
}

/** The board's box as measured, the page's raw safe-area insets and the gutter the page applies (px), and its slots. */
interface BoardInput {
    readonly box: BoardBox;
    readonly safeInsets: BoardEdges;
    readonly gutter: number;
    readonly slots: BoardSlots;
}

/** The board's sizes in px, by the stylesheet's length names (`rw` for `--rw`). */
type BoardLengths = Readonly<Record<string, number>>;

interface BoardGeometry {
    readonly family: BoardFamily;
    readonly chrome: ChromeTier;
    readonly gutter: number;
    readonly box: BoardBox;
    readonly lengths: BoardLengths;
    readonly tracks: BoardTracks;
    readonly strips: StripRooms | null;
}

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

/** The play switches' strip: three square chips and the names' button. */
const SWITCH_CHIPS = 4;

/** The replay's moves in the switches' place. */
const REPLAY_MOVES = 7;

/** An opponent's full hand's tiles. */
const HAND_TILES = 14;

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

/**
 * What the left river's reach takes past its river tiles (px) besides the tile edges in its two latest-discard gaps:
 * the gaps across the light and the river gap's rounding at most.
 */
const LEFT_REACH_GAPS = 2 * LATEST_DISCARD_GAP + 0.5;

/** The tile edges the left river's reach holds, in river tiles: one in each of its two latest-discard gaps. */
const LEFT_REACH_EDGES = 2 * TILE_EDGE_SHARE;

/**
 * The latest discard's gap along the light off a phone (px): the gap across it and the tile edge that falls into it,
 * the previous tile's on the left river and above a bottom river's row, the latest tile's own on the right river and
 * under a top river's row. A phone keeps the gap across: its edge is two pixels, and the reserve would cost it a pixel
 * of river tile at its floor.
 */
function latestDropGap(rw: number): number {
    return LATEST_DISCARD_GAP + Math.round(TILE_EDGE_SHARE * rw);
}

/** The right hand's origin from the band stands this far under the band's top margin (px). */
const RIGHT_FROM_BAND_GAP = 2;

/** A phone's switches' place holds the replay's five moves, wider than the play switches. */
const REPLAY_MOVES_ON_PHONE = 5;

/**
 * A phone's side fields beside the deepest strips: the notices' place (7.5 of its 11px ems) and its gaps to the strip
 * and the left river, and the decisions' column (two controls a row) and its gaps (px).
 */
const NOTICE_FIELD = 84;
const NOTICE_GAPS = 14;
const DECISIONS_COLUMN = 84;
const DECISIONS_GAPS = 12;

/** A side badge keeps at least this far off the top river's reserved third row (px). */
const SIDE_CLEAR = 16;

/** No phone's river tile passes this share of its height, nor goes under `PHONE_SMALLEST_RIVER` (px). */
const PHONE_MAX_RIVER_SHARE = 10;
const PHONE_SMALLEST_RIVER = 2;

/** The counters' place under the top strip: its gap above and below, and its height upright (px). */
const COUNTERS_GAP = 6;
const UPRIGHT_COUNTERS_H = 52;

/** Upright, the decisions' two rows keep these px between them and the own badge. */
const UPRIGHT_DECISIONS_GAPS = 16;

/** A panel keeps this far off the board's edges where nothing else is reserved there (px). */
const PANEL_GAP = 8;

/** A phone's live panel keeps this far off the notices' column beside it (px). */
const NOTICES_PANEL_GAP = 4;

/**
 * Upright, the replay's group stands this far off the right strip's deepest reach, and its row this far over the own
 * melds where it shares the own badge's row, else over the badge (px).
 */
const GROUP_STRIP_GAP = 8;
const GROUP_MELD_GAP = 2;
const GROUP_BADGE_GAP = 4;

/** A narrow upright board's centre keeps the room its text needs across (px). */
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

/** Off a phone, the own tile: `OWN_BY_RIVER_OFF_PHONE` river tiles within its family's fit, never under 4/3 of one. */
function offPhoneOwn(rw: number, ownFit: number): number {
    return Math.max(
        Math.floor(TILE_ASPECT * rw),
        Math.min(Math.floor(OWN_BY_RIVER_OFF_PHONE * rw), Math.floor(ownFit)),
    );
}

/** A desktop's own tile's fit: its shares of the board and a full hand across its row. */
function desktopOwnFit({ width, height }: BoardBox, { m, ownInline }: DesktopChrome): number {
    const ownCap = Math.min(DESKTOP_OWN_CAP_WIDTH * width, DESKTOP_OWN_CAP_HEIGHT * height);
    return Math.min(ownCap, (width - 2 * m - ownInline) / FULL_HAND);
}

/** An upright board's own tile's fit: its share of the height and a full hand across its row. */
function uprightOwnFit({ width, height }: BoardBox, { m, ownInline }: DesktopChrome): number {
    return Math.min(DESKTOP_OWN_CAP_HEIGHT * height, (width - 2 * m - ownInline) / FULL_HAND);
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
        ownBadgeH +
        OWN_BADGE_LANE +
        SWITCHES_CLEARANCE +
        switchGap +
        switchesPlace(tier) +
        sep +
        LEFT_REACH_GAPS;
    const tiles = SLOT_LEFT_REACH + LEFT_REACH_EDGES + OWN_ROW + BAND_TILE_SHARE;
    return Math.min((height - 2 * m - fixed) / tiles, (height - m - fixed) / (tiles + OWN_EDGE));
}

/** The switches' place: as tall and wide as the play switches or the replay's moves, so both boards size alike. */
function switchesPlace({ movesH, switchH }: DesktopChrome): number {
    return Math.max(switchH, movesH);
}

/** A row of controls this many and this large, this far apart. */
function rowWidth(count: number, size: number, gap: number): number {
    return count * size + (count - 1) * gap;
}

function switchesPlaceWidth({ chipGap, movesH, replayGap, switchH }: DesktopChrome): number {
    return Math.max(
        rowWidth(SWITCH_CHIPS, switchH, chipGap),
        rowWidth(REPLAY_MOVES, movesH, replayGap),
    );
}

/** An opponent's full hand along its line. */
function fullReach(rw: number, seat: StripSeat): number {
    return handLength({ drawn: true, rw, seat, tiles: HAND_TILES });
}

/** A side strip reserves one line even for four open kans at the meld face floor. */
function sideStripReach(rw: number): number {
    const gap = riverGap(rw) + MELD_GAP_EXTRA;
    return Math.max(
        fullReach(rw, "left"),
        ...[1, 2, 3, 4].map(
            (count) =>
                handLength({ drawn: true, rw, seat: "left", tiles: HAND_TILES - 3 * count }) +
                count * (gap + (3 + SIDEWAYS_UNITS) * FACE_FLOOR),
        ),
    );
}

/** A short desktop's centre width that keeps its bottom river clear of the switches' place starting at `left`. */
function centreBesideSwitches(tier: DesktopChrome, width: number, left: number): number {
    return 2 * (width / 2 - left - switchesPlaceWidth(tier) - SWITCHES_RIVER_GAP);
}

/**
 * Where the play switches start: past the left strip's stacked depth where the left hand's reach meets them, so
 * every meld runs on beside them; on a short desktop whose centre cannot narrow for that, past a tile-high line only.
 */
function switchesLeft(
    tier: DesktopChrome,
    {
        bandTop,
        centre,
        cy,
        rw,
        switchesTop,
        width,
    }: Readonly<Record<"bandTop" | "centre" | "cy" | "rw" | "switchesTop" | "width", number>>,
    short: boolean,
): number {
    const { m } = tier;
    const reach = sideStripReach(rw);
    const roomEnd = Math.min(bandTop, switchesTop);
    const leftStart = Math.max(
        belowTopStrip(m, rw),
        Math.min(cy - reach / 2, roomEnd - LEFT_HAND_GAP - reach),
    );
    if (leftStart + reach + STRIP_ROOM_GAP <= switchesTop) {
        return m;
    }
    const stacked = m + STACKED_DEPTH * rw + STEP_IN_GAP;
    return short && centreBesideSwitches(tier, width, stacked) < centre
        ? m + UPRIGHT_DEPTH * rw + STEP_IN_GAP
        : stacked;
}

/** The gap between the centre and a river, a whole pixel. */
function riverGap(rw: number): number {
    return Math.round(RIVER_GAP_SHARE * rw);
}

/** A top or bottom river's reach from the centre at its capacity: the gap and its rows. */
function riverRows(rw: number): number {
    return riverGap(rw) + (CORE_TILES / 2 - RIVER_GAP_SHARE) * rw;
}

/** How far down from the core's top the left river's capacity reaches, its sideways tile and latest discard counted. */
function leftRiverDrop(rw: number, drop: number): number {
    return 2 * drop + riverRows(rw) + (LEFT_REACH_TILES - CORE_TILES / 2) * rw + rw * TILE_ASPECT;
}

/**
 * The rivers' reserved reach, a row's sideways riichi tile and the latest discard's gap counted: a side
 * river's fourth row, a top or bottom river's third row run on to seven tiles, and the top river's third row's
 * centre-facing edge, which no gap moves toward the centre; and the latest discard's gaps.
 */
function riverLengths(
    { centre, cx, cy, rw }: Readonly<Record<"centre" | "cx" | "cy" | "rw", number>>,
    drop: number,
): [string, number][] {
    const hx = centre / 2;
    const gap = riverGap(rw);
    const sideReach = (SIDE_REACH_TILES / 2) * rw + LATEST_DISCARD_GAP;
    const runOnReach = RUN_ON_REACH_TILES * rw + LATEST_DISCARD_GAP;
    return [
        ["latest-discard-gap", LATEST_DISCARD_GAP],
        ["latest-drop-gap", drop],
        ["reach-bottom-right", cx - hx + runOnReach],
        ["reach-left", leftReach(cx, centre, rw)],
        ["reach-right", cx + hx + gap + sideReach],
        ["reach-top-left", cx + hx - runOnReach],
        ["reach-top-row3", cy - centre / 2 - gap - ROWS_BEFORE_RUN_ON * rw],
        ["river-across", RIVER_ROWS["run-on"] * rw * TILE_ASPECT],
        ["river-along", RIVER_ROW_SIZE * rw],
    ];
}

/** Where the left river's reach ends, toward the board's left edge. */
function leftReach(cx: number, centre: number, rw: number): number {
    return cx - centre / 2 - riverGap(rw) - (SIDE_REACH_TILES / 2) * rw - LATEST_DISCARD_GAP;
}

/** The page's cog's side, from the river tile within its floor and cap. */
function menuSize(rw: number): number {
    return Math.min(MENU_MAX, Math.max(MENU_MIN, MENU_RIVER_SHARE * rw));
}

/** The cog's side; it reserves no room, standing over whatever lies under it. */
function cornerLengths(rw: number): [string, number][] {
    return [["menu-size", menuSize(rw)]];
}

/** The panel's free box, as the overlay's insets from the board's edges. */
function panelLengths({ bottom, left, right, top }: BoardEdges): [string, number][] {
    return [
        ["overlay-bottom", bottom],
        ["overlay-left", left],
        ["overlay-right", right],
        ["overlay-top", top],
    ];
}

/** Where a replay's moves' row starts over the switches' place. */
function movesRowTop(switchesBottom: number, movesH: number, replayGap: number): number {
    return switchesBottom - movesH - replayGap;
}

/** What a desktop's panel is placed from, in px. */
interface DesktopPanelRoom {
    readonly chrome: ChromeTier;
    readonly foregroundTop: number;
    readonly height: number;
    readonly reachLeft: number;
    readonly rw: number;
    readonly short: boolean;
    readonly slots: BoardSlots;
    readonly switchesBottom: number;
    readonly switchesLeft: number;
    readonly tier: DesktopChrome;
}

/**
 * A desktop's panel's free box, over the cog where it reaches the corner. At a desktop's chrome it starts past the left
 * river's reach (the notices' field); a replay's stands above the band too, and past its moves where they hold the
 * switches' place. On a narrow desktop a live panel stands between the side strips, past the left river's reach; a
 * replay's above its moves' row.
 */
function desktopPanel(room: DesktopPanelRoom): BoardEdges {
    const { chrome, height, rw, slots, tier } = room;
    const { m, movesH, replayGap } = tier;
    const replay = slots.band === "replay";
    if (chrome !== "small") {
        const movesEnd =
            replay && room.short ? room.switchesLeft + REPLAY_MOVES * (movesH + replayGap) : 0;
        return {
            bottom: replay ? height - room.foregroundTop : PANEL_GAP,
            left: Math.max(room.reachLeft, movesEnd),
            right: PANEL_GAP,
            top: PANEL_GAP,
        };
    }
    if (replay) {
        return {
            bottom: height - movesRowTop(room.switchesBottom, movesH, replayGap),
            left: PANEL_GAP,
            right: PANEL_GAP,
            top: PANEL_GAP,
        };
    }
    const besideStrip = m + STACKED_DEPTH * rw + PANEL_GAP;
    return {
        bottom: PANEL_GAP,
        left: Math.max(room.reachLeft, besideStrip),
        right: besideStrip,
        top: PANEL_GAP,
    };
}

/** What a family's sizes are solved for: the board's settled box, its family and chrome, and its page's slots. */
interface BoardFrame {
    readonly box: BoardBox;
    readonly chrome: ChromeTier;
    readonly family: BoardFamily;
    readonly slots: BoardSlots;
}

/** The desktop and short desktop's root sizes and the lengths the stylesheet reads with them, in px. */
function desktopLengths(frame: BoardFrame): BoardLengths {
    const { box, chrome, family } = frame;
    const { width, height } = box;
    const short = family === "short-desktop";
    const tier = { ...DESKTOP_CHROME[chrome], sep: DESKTOP_CHROME[chrome].badgeGap };
    const { bandGap, m, ownBadgeH, switchGap } = tier;
    const ownFit = desktopOwnFit(box, tier);
    const coreCap = DESKTOP_CORE_CAP * height;
    const coreRoomW = width - 2 * m - CORE_ROOM_SIDES;
    const rowRiseFixed = chrome === "small" ? ownBadgeH + OWN_BADGE_LANE + switchGap - bandGap : 0;
    const rooms = { coreCap, coreRoomW, height, ownFit, rowRiseFixed, tier };
    const familyRiverTile = short ? switchesRiverTile(rooms) : bandRiverTile(rooms);
    const largestRiver = Math.min(sharedRiverTile(rooms), familyRiverTile);
    let rw = Math.max(1, Math.floor(largestRiver));
    let layout = desktopLayout(frame, tier, rw);
    while (rw > 1 && !layout.fits) {
        rw -= 1;
        layout = desktopLayout(frame, tier, rw);
    }
    return layout.lengths;
}

function desktopLayout(
    { box, chrome, family, slots }: BoardFrame,
    tier: DesktopChrome,
    rw: number,
): { readonly fits: boolean; readonly lengths: BoardLengths } {
    const { width, height } = box;
    const short = family === "short-desktop";
    const { bandGap, controlH, coreGap, m, ownBadgeH, ownInline, sep, switchGap } = tier;
    const coreCap = DESKTOP_CORE_CAP * height;
    const coreRoomW = width - 2 * m - CORE_ROOM_SIDES;
    const rh = rw * TILE_ASPECT;
    const ow = offPhoneOwn(rw, desktopOwnFit(box, tier));
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

    const coreRoom = Math.min(
        coreRoomH - rh,
        short ? Infinity : coreRoomBand - rh,
        coreCap,
        coreRoomW - SIDE_REACH_TILES * rw,
    );
    const centreTarget = RIVER_ROW_SIZE * rw;
    const drop = latestDropGap(rw);
    const riverHeight = 2 * (drop + riverRows(rw));
    const centre = Math.min(centreTarget, coreRoom - riverHeight);
    const core = centre + riverHeight;
    const coreTopSlot = m + rh + sep;
    const coreTopFree = (coreRoomH - rh - core) / 2;
    const switchesTop = switchesBottom - switchesPlace(tier);
    const coreTopRoom = switchesTop - SWITCHES_CLEARANCE - coreTopSlot - leftRiverDrop(rw, drop);
    const coreTop = short
        ? coreTopSlot + Math.max(0, Math.min(coreTopFree, coreTopRoom))
        : Math.min(coreTopSlot + coreTopFree, handTop - bandReserve - core);
    const cy = coreTop + core / 2;
    const bandTop = handTop - bandGap - controlH - rowRise - bandLift;
    const switchesX = switchesLeft(tier, { bandTop, centre, cy, rw, switchesTop, width }, short);
    const centreBySwitches = short ? centreBesideSwitches(tier, width, switchesX) : Infinity;
    const panel = desktopPanel({
        chrome,
        foregroundTop: bandTop - bandGap,
        height,
        reachLeft: leftReach(width / 2, centre, rw),
        rw,
        short,
        slots,
        switchesBottom,
        switchesLeft: switchesX,
        tier,
    });

    const lengths = Object.fromEntries([
        ...chromeLengths(tier),
        ...cornerLengths(rw),
        ...panelLengths(panel),
        ...replayLengths(slots, chrome, tier),
        ["band-bottom", bandBottom],
        ["band-gap", bandGap],
        ["band-lift", bandLift],
        ["c", centre],
        ["control-h", controlH],
        ["core-top", coreTop],
        ["cx", width / 2],
        ["cy", cy],
        ["g", riverGap(rw)],
        ["h", centre / 2],
        ["hand-top", handTop],
        ["hx", centre / 2],
        ["m", m],
        ["oh", oh],
        ["ow", ow],
        ["own-badge-h", ownBadgeH],
        ["own-inline", ownInline],
        ["own-meld-rise", ownMeldRise],
        ["own-meld-tile", ownMeldTile],
        ["own-rise", ownRise],
        ...riverLengths({ centre, cx: width / 2, cy, rw }, drop),
        ["rh", rh],
        ["row-rise", rowRise],
        ["rw", rw],
        ["switches-bottom", switchesBottom],
        ["w", centre],
    ]);
    return {
        fits: centre >= centreTarget && centre <= centreBySwitches && (!short || coreTopRoom >= 0),
        lengths,
    };
}

/** What an upright board's replay group's row is placed from, in px. */
interface UprightGroupRoom {
    readonly chrome: ChromeTier;
    readonly handTop: number;
    readonly ow: number;
    readonly ownMeldRise: number;
    readonly ownRise: number;
    readonly rw: number;
    readonly tier: DesktopChrome;
    readonly width: number;
}

/** A replay's moves' row: a smaller board's five moves, else seven. */
function replayMovesWidth(chrome: ChromeTier, movesH: number, replayGap: number): number {
    return rowWidth(chrome === "small" ? REPLAY_MOVES_ON_PHONE : REPLAY_MOVES, movesH, replayGap);
}

/** A replay's group: its moves and two more controls, its gap between them. */
function replayGroupWidth(chrome: ChromeTier, movesH: number, replayGap: number): number {
    return replayMovesWidth(chrome, movesH, replayGap) + 2 * (movesH + replayGap);
}

function replayLengths(
    slots: BoardSlots,
    chrome: ChromeTier,
    { movesH, replayGap }: Readonly<Record<"movesH" | "replayGap", number>>,
): [string, number][] {
    return slots.band === "replay"
        ? [
              ["moves-w", replayMovesWidth(chrome, movesH, replayGap)],
              ["replay-gap", replayGap],
          ]
        : [];
}

function uprightGroupLane(room: UprightGroupRoom): number {
    const { bandGap, m, movesH, replayGap } = room.tier;
    const groupW = replayGroupWidth(room.chrome, movesH, replayGap);
    const groupLeft = room.width - m - sideLaneReserve(room.rw) - GROUP_STRIP_GAP - groupW;
    return groupLeft - bandGap - (room.width - FULL_HAND * room.ow) / 2;
}

/**
 * Where an upright replay's group's row ends: in the own badge's row over the melds where the group leaves the badge an
 * ordinary name beside the centred hand, else over the badge.
 */
function uprightGroupBottom(room: UprightGroupRoom): number {
    return uprightGroupLane(room) >= room.tier.sideLaneMin
        ? room.handTop - room.ownMeldRise - GROUP_MELD_GAP
        : room.handTop - room.ownRise - GROUP_BADGE_GAP;
}

/**
 * An upright board's panel's free box: from the top, over the cog, and above the foreground band, which a live board's
 * notices take over a panel, or above a replay's group and status rows.
 */
function uprightPanel(
    room: UprightGroupRoom & { readonly slots: BoardSlots },
    height: number,
): BoardEdges {
    const { controlH, bandGap, movesH, replayGap } = room.tier;
    const above =
        room.slots.band === "replay"
            ? uprightGroupBottom(room) - 2 * (movesH + replayGap)
            : room.handTop - 2 * bandGap - controlH;
    return {
        bottom: height - above,
        left: PANEL_GAP,
        right: PANEL_GAP,
        top: PANEL_GAP,
    };
}

/**
 * An upright board's root sizes and the lengths the stylesheet reads with them, in px: its core under the counters and
 * above the decisions' two rows and the notices' place, its centre never under `UPRIGHT_CENTRE_MIN`.
 */
function uprightLengths(frame: BoardFrame): BoardLengths {
    const { box, chrome } = frame;
    const { width, height } = box;
    const tier = { ...DESKTOP_CHROME[chrome], ...UPRIGHT_CHROME };
    const { controlH, m, ownBadgeH } = tier;
    const ownFit = uprightOwnFit(box, tier);
    const coreCap = DESKTOP_CORE_CAP * height;
    const coreRoomW = width - 2 * m - CORE_ROOM_SIDES;
    const underStrip = m + COUNTERS_GAP + UPRIGHT_COUNTERS_H;
    const fixed =
        ownBadgeH +
        2 * controlH +
        UPRIGHT_DECISIONS_GAPS +
        OWN_BADGE_LANE +
        UPRIGHT_NOTICE_GAP +
        UPRIGHT_NOTICE_ROOM +
        underStrip;
    const edgeTiles = UPRIGHT_TILES + DESKTOP_SPARE * OWN_EDGE;
    let rw = Math.floor(
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
    let lengths = uprightLayout(frame, rw);
    while (rw > 1 && (lengths["c"] ?? 0) < Math.max(UPRIGHT_CENTRE_MIN, RIVER_ROW_SIZE * rw)) {
        rw -= 1;
        lengths = uprightLayout(frame, rw);
    }
    return lengths;
}

function uprightLayout({ box, chrome, slots }: BoardFrame, rw: number): BoardLengths {
    const { width, height } = box;
    const tier = { ...DESKTOP_CHROME[chrome], ...UPRIGHT_CHROME };
    const { bandGap, controlH, coreGap, m, ownBadgeH, ownInline, sep } = tier;
    const coreCap = DESKTOP_CORE_CAP * height;
    const coreRoomW = width - 2 * m - CORE_ROOM_SIDES;
    const underStrip = m + COUNTERS_GAP + UPRIGHT_COUNTERS_H;
    const rh = rw * TILE_ASPECT;
    const ow = offPhoneOwn(rw, uprightOwnFit(box, tier));
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
    const drop = latestDropGap(rw);
    const centre = core - 2 * (drop + riverRows(rw));
    const coreFloor = underStrip + stripDepth;
    const coreTopSlot = m + rh + sep;
    const coreTopFree = (coreRoomH - rh - core) / 2;
    const coreTop = Math.max(
        coreFloor,
        Math.min(coreTopSlot + coreTopFree, handTop - bandReserve - core),
    );
    const cy = coreTop + core / 2;
    const groupRoom = { chrome, handTop, ow, ownMeldRise, ownRise, rw, tier, width };
    const replay = slots.band === "replay";
    const groupLane = uprightGroupLane(groupRoom);
    const halfHand = (FULL_HAND * ow) / 2;

    return Object.fromEntries([
        ...chromeLengths(tier),
        ...cornerLengths(rw),
        ...panelLengths(uprightPanel({ ...groupRoom, slots }, height)),
        ...replayLengths(slots, chrome, tier),
        [
            "actions-bottom",
            replay ? uprightGroupBottom(groupRoom) : handTop - ownRise - GROUP_BADGE_GAP,
        ],
        ["band-gap", bandGap],
        ["c", centre],
        ["control-h", controlH],
        ["core-top", coreTop],
        ["cx", width / 2],
        ["cy", cy],
        ["g", riverGap(rw)],
        ["h", centre / 2],
        ["hand-top", handTop],
        ["hx", centre / 2],
        ["m", m],
        ["notices-bottom", noticesBottom],
        ["oh", oh],
        ["ow", ow],
        ["own-badge-h", ownBadgeH],
        ["own-inline", ownInline],
        [
            "own-lane",
            replay && groupLane >= tier.sideLaneMin ? Math.min(halfHand, groupLane) : halfHand,
        ],
        ["own-meld-rise", ownMeldRise],
        ["own-meld-tile", ownMeldTile],
        ["own-rise", ownRise],
        ...riverLengths({ centre, cx: width / 2, cy, rw }, drop),
        ["rh", rh],
        ["rw", rw],
        ["w", centre],
    ]);
}

/** How far in from the board's side edge a side badge stands: past its strip's line by a badge gap. */
function sideBadgeX({ badgeGap, m }: DesktopChrome, rw: number): number {
    return m + STACKED_DEPTH * rw + badgeGap;
}

/** Side tiles and an equally deep buffer before interior controls, retained as melds scale within their line. */
function sideLaneReserve(rw: number): number {
    return STACKED_DEPTH * rw + SIDE_LANE_GAP + STACKED_DEPTH * Math.max(rw, FACE_FLOOR);
}

/** A phone's chrome at its river tile: the small tier's px, growing with the river tile past `PHONE_CHROME_RIVER`. */
function phoneChrome(rw: number): DesktopChrome {
    const scale = Math.max(1, rw / PHONE_CHROME_RIVER);
    const control = PHONE_CHROME.controlH * scale;
    return {
        ...PHONE_CHROME,
        badgeH: PHONE_CHROME.badgeH * scale,
        controlH: control,
        countersW: PHONE_CHROME.countersW * scale,
        doraW: PHONE_CHROME.doraW * scale,
        movesH: control,
        ownBadgeH: PHONE_CHROME.ownBadgeH * scale,
        ownPillH: PHONE_CHROME.ownPillH * scale,
        pillH: PHONE_CHROME.pillH * scale,
        switchH: control,
        timerW: PHONE_CHROME.timerW * scale,
    };
}

/** The counters' height: the indicator's, and the padding and rim above and below it. */
function countersHeight({ countersFrame, doraW }: DesktopChrome): number {
    return doraW * TILE_ASPECT + countersFrame;
}

/** Under the top strip's stacked depth and a gap: the counters' top, and the highest a side hand starts. */
function belowTopStrip(m: number, rw: number): number {
    return m + STACKED_DEPTH * rw + COUNTERS_GAP;
}

/** Where the side badges start: under the counters, which stand over the left one from its edge. */
function sidesStart(tier: DesktopChrome, rw: number): number {
    return belowTopStrip(tier.m, rw) + countersHeight(tier) + COUNTERS_GAP;
}

/** The counters' top: directly over the left badge, never above the top strip's depth and a gap. */
function countersTop(tier: DesktopChrome, rw: number, leftBadgeTop: number): number {
    return Math.max(belowTopStrip(tier.m, rw), leftBadgeTop - countersHeight(tier) - COUNTERS_GAP);
}

/** The chrome px the stylesheet draws with, by its names. */
function chromeLengths(tier: DesktopChrome): [string, number][] {
    return [
        ["action-min-w", tier.actionMinW],
        ["badge-h", tier.badgeH],
        ["chip-gap", tier.chipGap],
        ["counters-h", countersHeight(tier)],
        ["counters-w", tier.countersW],
        ["dora-w", tier.doraW],
        ["moves-h", tier.movesH],
        ["own-pill-h", tier.ownPillH],
        ["pill-h", tier.pillH],
        ["side-lane-min", tier.sideLaneMin],
        ["switch-h", tier.switchH],
        ["timer-w", tier.timerW],
        ["win-min-w", tier.winMinW],
    ];
}

/** What a phone's right hand runs in: the band's top, its full reach and what bounds it (px). */
type PhoneRightRoom = Readonly<
    Record<"bandTop" | "cy" | "fromBand" | "ownRowTop" | "reach", number>
>;

function phoneRightRoom(
    sizes: Readonly<
        Record<"bandGap" | "controlH" | "cy" | "handTop" | "ownMeldRise" | "rw", number>
    >,
): PhoneRightRoom {
    const { bandGap, controlH, handTop } = sizes;
    return {
        bandTop: handTop - bandGap - controlH,
        cy: sizes.cy,
        fromBand: handTop - 2 * bandGap - controlH + RIGHT_FROM_BAND_GAP,
        ownRowTop: handTop - sizes.ownMeldRise - SWITCHES_CLEARANCE,
        reach: sideStripReach(sizes.rw),
    };
}

/**
 * Where a phone's right hand runs, from its full reach: centred between the top margin and the band, else up from the
 * band, else from the top margin across the band, whose row then steps in past it.
 */
function phoneRightHand({ bandTop, cy, fromBand, reach }: PhoneRightRoom): {
    readonly origin: number;
    readonly bandCrossed: boolean;
} {
    const top = PHONE_CHROME.m + reach;
    const origin = Math.min(Math.max(fromBand, top), Math.max(top, cy + reach / 2));
    return { bandCrossed: origin > bandTop, origin };
}

/**
 * A phone's panel's free box: at the top, over the cog; a live panel short of the notices' column beside it, a
 * replay's above its moves' row.
 */
function phonePanel(
    slots: BoardSlots,
    height: number,
    lengths: Readonly<Record<"bandShift" | "movesH" | "switchesBottom", number>>,
): BoardEdges {
    const { replayGap } = PHONE_CHROME;
    const replay = slots.band === "replay";
    return {
        bottom: replay
            ? height - movesRowTop(lengths.switchesBottom, lengths.movesH, replayGap)
            : PANEL_GAP,
        left: 0,
        right: replay ? PANEL_GAP : NOTICES_BESIDE_PANEL + NOTICES_PANEL_GAP + lengths.bandShift,
        top: PANEL_GAP,
    };
}

/** A phone's lengths at a river and own tile, in px, and whether its places fit them. */
function phoneLayout(
    frame: BoardFrame,
    rw: number,
    ow: number,
): { readonly fits: boolean; readonly lengths: BoardLengths } {
    const { box, slots } = frame;
    const { height, width } = box;
    const chrome = phoneChrome(rw);
    const { bandGap, controlH, coreGap, m, ownBadgeH, sep, switchGap } = chrome;
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
    const rows = riverRows(rw);
    const centreTop = coreTop + LATEST_DISCARD_GAP + rows;
    const heightRoom = handTop - coreGap - LATEST_DISCARD_GAP - rows - centreTop;
    const sideReach = riverGap(rw) + (SIDE_REACH_TILES / 2) * rw + LATEST_DISCARD_GAP;
    const fieldHalf = width / 2 - sideReach - m - sideLaneReserve(rw);
    const runOnReach = RUN_ON_REACH_TILES * rw + LATEST_DISCARD_GAP;
    const leftBadgeX = sideBadgeX(chrome, rw);
    const laneHalf =
        chrome.sideLaneMin + Math.max(SIDE_CLEAR, rw) + leftBadgeX + runOnReach - width / 2;
    const centreMin = Math.max(PHONE_CENTRE_MIN, RIVER_ROW_SIZE * rw, 2 * laneHalf);
    const switchesRight =
        m +
        STACKED_DEPTH * rw +
        STEP_IN_GAP +
        replayMovesWidth("small", chrome.movesH, chrome.replayGap);
    const clearHalf = width / 2 - sideReach - SWITCHES_CLEARANCE - switchesRight;
    const besideSwitches = clearHalf >= Math.max(centreMin / 2, laneHalf);
    const halfRoom = Math.min(
        fieldHalf - NOTICE_FIELD - NOTICE_GAPS,
        fieldHalf - DECISIONS_COLUMN - DECISIONS_GAPS,
        besideSwitches ? clearHalf : Infinity,
    );
    const centre = Math.min(heightRoom, 2 * halfRoom);
    const leftRiverEnd = coreTop + leftRiverDrop(rw, LATEST_DISCARD_GAP);
    const cy = centreTop + centre / 2;
    const rightRoom = phoneRightRoom({
        bandGap,
        controlH,
        cy,
        handTop,
        ownMeldRise,
        rw,
    });
    const right = phoneRightHand(rightRoom);
    const placesFit =
        centre >= centreMin &&
        laneHalf <= halfRoom &&
        leftRiverEnd + SWITCHES_CLEARANCE <= (besideSwitches ? handTop - ownRise : switchesTop) &&
        belowTopStrip(m, rw) + rightRoom.reach <= height - m &&
        right.origin <= rightRoom.ownRowTop;
    const bandShift = right.bandCrossed ? rh + STEP_IN_GAP : 0;
    const panel = phonePanel(slots, height, {
        bandShift,
        movesH: chrome.movesH,
        switchesBottom,
    });

    const lengths = Object.fromEntries([
        ...chromeLengths(chrome),
        ...cornerLengths(rw),
        ...panelLengths(panel),
        ...replayLengths(slots, "small", chrome),
        ["band-bottom", bandBottom],
        ["band-gap", bandGap],
        ["band-lift", 0],
        ["band-shift", bandShift],
        ["c", centre],
        ["control-h", controlH],
        ["core-top", coreTop],
        ["cx", width / 2],
        ["cy", cy],
        ["g", riverGap(rw)],
        ["h", centre / 2],
        ["hand-top", handTop],
        ["hx", centre / 2],
        ["m", m],
        ["oh", oh],
        ["ow", ow],
        ["own-badge-h", ownBadgeH],
        ["own-inline", 0],
        ["own-meld-rise", ownMeldRise],
        ["own-meld-tile", ownMeldTile],
        ["own-rise", ownRise],
        ...riverLengths({ centre, cx: width / 2, cy, rw }, LATEST_DISCARD_GAP),
        ["rh", rh],
        ["row-rise", 0],
        ["rw", rw],
        ["switches-bottom", switchesBottom],
        ["w", centre],
    ]);
    const { rightBadgeTop } = landscapeBadges(
        { at: (name) => lengths[name] ?? 0, frame, tier: chrome },
        bandBottom,
    );
    const offersRoom = bandBottom - rightBadgeTop - chrome.badgeH - ACTIONS_GAP;
    return { fits: placesFit && offersRoom >= phoneOffersHeight(controlH), lengths };
}

/**
 * A phone's root sizes and the lengths the stylesheet reads with them, in px: the largest river tile that fits, then
 * the largest own tile that fits with it, at most as wide as a full hand clear of both side strips' stacked depth and at
 * least 4/3 of the river tile, never under `PHONE_OWN_FLOOR`, which wins where both cannot hold; the smallest pair where
 * none fits. A pair fits only where the decisions' place under the right badge holds the worst offers' stack.
 */
function phoneLengths(frame: BoardFrame): BoardLengths {
    const { box } = frame;
    for (
        let rw = Math.floor(box.height / PHONE_MAX_RIVER_SHARE);
        rw >= PHONE_SMALLEST_RIVER;
        rw -= 1
    ) {
        const clearFit = Math.floor(
            (box.width - 2 * (PHONE_CHROME.m + STACKED_DEPTH * rw + STEP_IN_GAP)) / FULL_HAND,
        );
        const largest = Math.max(PHONE_OWN_FLOOR, clearFit);
        const least = Math.max(PHONE_OWN_FLOOR, Math.ceil(TILE_ASPECT * rw));
        for (let ow = largest; ow >= least; ow -= 1) {
            const { fits, lengths } = phoneLayout(frame, rw, ow);
            if (fits) {
                return lengths;
            }
        }
    }
    return phoneLayout(frame, PHONE_SMALLEST_RIVER, PHONE_OWN_FLOOR).lengths;
}

/** A slot's box on the board, px from its top-left corner. */
interface BoardRect {
    readonly left: number;
    readonly top: number;
    readonly right: number;
    readonly bottom: number;
}

/** The slots GameBoard places on the shell's grid, by their areas' names. */
type ShellSlot =
    | "actions"
    | "corner"
    | "field"
    | "field-beside"
    | "hand"
    | "switches"
    | "strip-left"
    | "strip-right"
    | "strip-top";

/** The shell's grid: its columns and rows as templates whose named lines are each slot's edges. */
interface BoardTracks {
    readonly columns: string;
    readonly rows: string;
}

/**
 * A family's slots: their areas on the board, the lengths the stylesheet places their contents from, and the rooms the
 * opponents' strips lay their melds out in.
 */
interface BoardShell {
    readonly areas: Readonly<Record<ShellSlot, BoardRect>>;
    readonly lengths: readonly [string, number][];
    readonly strips: StripRooms;
}

/** What the slots are placed from: the board's frame, its family's lengths by name, and its chrome. */
interface ShellRoom {
    readonly frame: BoardFrame;
    readonly at: (name: string) => number;
    readonly tier: DesktopChrome;
}

/** The decisions' gap between controls and a win's rise past a control (px). */
const DECISION_GAP = 12;
const WIN_RISE = 4;

/** The decisions' least row (a win, four offers and the timer) and a short desktop's tallest column (five offers). */
const DECISION_OFFERS = 4;
const DECISION_ROWS = 6;

/** A narrow band end keeps this much room for its controls (px). */
const ACTIONS_ROW_MIN = 180;

/** The band end stands this far past the rivers' reach and a phone's under the right badge (px). */
const ACTIONS_GAP = 6;

/** A phone's decision row and the gap between its decisions (px); the stylesheet's `$row` and `$small-decision-gap`. */
const PHONE_DECISION_ROW = 40;
const PHONE_DECISION_GAP = 6;

/** A phone's worst offers stand as a win over this many rows of paired calls, over the band's row. */
const PHONE_CALL_ROWS = 2;

/** The top badge stands this far past a river tile's edge, the side badges a step this far under its pill (px). */
const TOP_BADGE_GAP = 6;
const SIDE_STEP_GAP = 8;

/** A short desktop's side badges keep this far off the decisions' tallest column (px). */
const BADGE_DECISIONS_GAP = 6;

/** The own badge's lane keeps half a river tile off the bottom river, never under this (px). */
const RIVER_CLEAR_MIN = 10;

/** The notices' field's gap to what it stands past (px), by the board's chrome and family. */
const FIELD_GAP: Readonly<Record<ChromeTier | "phone", number>> = {
    large: 16,
    phone: 6,
    regular: 16,
    small: 8,
};

/** The field keeps this far off the left river and off the band (a phone's less) (px). */
const FIELD_RIVER_GAP = 8;
const FIELD_BAND_GAP = 24;
const PHONE_FIELD_BAND_GAP = 8;

/** Over a panel, a phone's or an upright board's notices keep this far off the band and the own row (px). */
const BESIDE_GAP = 4;

/** Upright, the band end and the field keep this far off the right strip's deepest reach (px). */
const UPRIGHT_STRIP_GAP = 8;

/** Upright, the right hand's lowest start keeps these px under the top badge's pill and over its own badge. */
const UPRIGHT_PILL_GAP = 6;
const UPRIGHT_BADGE_GAP = 4;

/** A length past which a CSS comparison counted half a pixel (px). */
const HALF_PIXEL = 0.5;

/** Where the river's rows meet the board, from the tile slice's shape. */
const RIVER_ROWS_RUN_ON = RIVER_ROWS["run-on"];
const ROW_BEFORE_SIDEWAYS = RIVER_ROW_SIZE - 1;

/** The own badge's lane, and where the decisions' row starts after it where the lane is its own. */
function ownLane(
    { at, tier }: ShellRoom,
    { ownLead, plateReach }: Readonly<Record<"ownLead" | "plateReach", number>>,
): { readonly lane: number; readonly end: number } {
    const rw = at("rw");
    const laneFree = tier.sideLaneMin - plateReach + ownLead > 0;
    const bottomRiverEnd =
        at("cy") + at("h") + at("g") + RIVER_ROWS_RUN_ON * at("rh") + at("latest-drop-gap");
    const besideRiver = bottomRiverEnd - at("hand-top") + at("own-rise") > 0;
    const riverLane = at("cx") - at("hx") - Math.max(RIVER_CLEAR_MIN, rw / 2) - ownLead;
    const lane = Math.min(
        (FULL_HAND * at("ow")) / 2,
        besideRiver ? riverLane : Infinity,
        laneFree ? Infinity : plateReach - ownLead,
    );
    return { end: laneFree ? ownLead + lane + at("band-gap") : -Infinity, lane };
}

/** The height of a phone's worst offers' stack at its band's control height (px). */
function phoneOffersHeight(controlH: number): number {
    return (
        PHONE_DECISION_ROW +
        WIN_RISE +
        PHONE_CALL_ROWS * PHONE_DECISION_ROW +
        controlH +
        (PHONE_CALL_ROWS + 1) * PHONE_DECISION_GAP
    );
}

/** Where the opponents' badges stand off an upright board, and the left one's lane (px). */
type LandscapeBadges = Readonly<
    Record<"rightBadgeTop" | "sideBadgeTop" | "sideLane" | "topBadgeTop", number>
>;

/**
 * The opponents' badges off an upright board: the top one under its hand past a river tile's edge; the side ones at
 * the strips' start a step under the top one's pill (a short desktop's only where the decisions' tallest column leaves
 * room under the right one, a phone's right one alone), else past the top river's reserved third row where the lane at
 * the start is short of an ordinary name; and the left one's lane.
 */
function landscapeBadges(room: ShellRoom, rowBottom: number): LandscapeBadges {
    const { at, frame, tier } = room;
    const { family } = frame;
    const m = at("m");
    const rw = at("rw");
    const { badgeH, pillH } = tier;
    const topBadgeTop = m + at("rh") + TILE_EDGE_SHARE * rw + TOP_BADGE_GAP;
    const stepped = topBadgeTop + pillH + SIDE_STEP_GAP;
    const decisionsTop =
        rowBottom - DECISION_ROWS * at("control-h") - (DECISION_ROWS - 1) * DECISION_GAP - WIN_RISE;
    const shortStep = decisionsTop - BADGE_DECISIONS_GAP - badgeH - stepped > 0 ? stepped : 0;
    const sideStep = {
        desktop: stepped,
        phone: 0,
        "short-desktop": shortStep,
        upright: 0,
    }[family];
    const sideClear = Math.max(SIDE_CLEAR, rw);
    const leftBadgeX = sideBadgeX(tier, rw);
    const laneAtStart = at("reach-top-left") - sideClear - leftBadgeX;
    const narrow = tier.sideLaneMin - laneAtStart > 0;
    const topRowsLeft =
        at("cx") + at("hx") - ROW_BEFORE_SIDEWAYS * rw - at("rh") - LATEST_DISCARD_GAP;
    const laneBelow = topRowsLeft - sideClear - leftBadgeX;
    const sideStart = sidesStart(tier, rw);
    const sideBadgeTop = Math.max(
        sideStart,
        sideStep,
        narrow ? at("reach-top-row3") + sideClear : sideStart,
    );
    const rightBadgeTop =
        family === "phone"
            ? Math.max(sideBadgeTop, topBadgeTop + pillH + TOP_BADGE_GAP)
            : sideBadgeTop;
    const sideLane = Math.max(laneAtStart, Math.min(laneBelow, narrow ? Infinity : 0));
    return {
        rightBadgeTop,
        sideBadgeTop,
        sideLane: Math.min(tier.sideCardW, sideLane),
        topBadgeTop,
    };
}

/** Where the left hand's full reach starts, where its room ends and where the play switches start. */
function landscapeLeft(
    { at, frame, tier }: ShellRoom,
    { bandTop, switchesTop }: Readonly<Record<"bandTop" | "switchesTop", number>>,
): Readonly<Record<"leftRoomEnd" | "leftStart" | "switchesLeft", number>> {
    const m = at("m");
    const rw = at("rw");
    const reach = sideStripReach(rw);
    if (frame.family !== "phone") {
        const roomEnd = Math.min(bandTop, switchesTop);
        return {
            leftRoomEnd: Math.max(bandTop, switchesTop),
            leftStart: Math.max(
                belowTopStrip(m, rw),
                Math.min(at("cy") - reach / 2, roomEnd - LEFT_HAND_GAP - reach),
            ),
            switchesLeft: switchesLeft(
                tier,
                { bandTop, centre: at("c"), cy: at("cy"), rw, switchesTop, width: frame.box.width },
                frame.family === "short-desktop",
            ),
        };
    }
    const leftStart = belowTopStrip(m, rw);
    const meets = leftStart + reach + STRIP_ROOM_GAP > switchesTop;
    return {
        leftRoomEnd: meets ? bandTop : Math.min(bandTop, switchesTop),
        leftStart,
        switchesLeft: meets ? m + STACKED_DEPTH * rw + STEP_IN_GAP : m,
    };
}

/**
 * A desktop's decisions' place: after the switches and the own badge's lane where it is its own (a short desktop's
 * past the bottom and right rivers' reach too), to the hand's right end or as far past it as a full row of offers (or
 * a replay's group) needs; its controls stand at its bottom.
 */
function desktopActions(
    { at, frame, tier }: ShellRoom,
    own: Readonly<Record<"badgeEnd" | "handRight" | "rowBottom" | "switchesRight", number>>,
): BoardRect {
    const { box, family, slots } = frame;
    const { width } = box;
    const m = at("m");
    const short = family === "short-desktop";
    const pastRivers = Math.max(at("reach-bottom-right"), at("reach-right")) + ACTIONS_GAP;
    const left = Math.max(
        own.switchesRight + at("band-gap"),
        own.badgeEnd,
        short ? pastRivers : -Infinity,
    );
    const need =
        slots.band === "replay"
            ? replayGroupWidth(frame.chrome, tier.movesH, tier.replayGap)
            : tier.winMinW +
              DECISION_OFFERS * tier.actionMinW +
              tier.timerW +
              (DECISION_OFFERS + 1) * DECISION_GAP;
    const right = short
        ? Math.max(
              m + STACKED_DEPTH * at("rw") + DECISION_GAP,
              Math.min(width - own.handRight, width - left - ACTIONS_ROW_MIN),
          )
        : Math.max(m, Math.min(width - own.handRight, width - left - need));
    return { bottom: own.rowBottom, left, right: width - right, top: 0 };
}

/**
 * Over a panel, a phone's or an upright board's notices: a column under the right strip's end, from the band's top or
 * the right hand's origin to the own row, beside the band row where it steps in.
 */
function besideField(
    { at, frame }: ShellRoom,
    right: Readonly<Record<"bandShift" | "foregroundTop" | "origin", number>>,
): BoardRect {
    const m = at("m");
    const top =
        right.bandShift > 0 ? right.foregroundTop : Math.max(right.foregroundTop, right.origin);
    const end = frame.box.width - m - right.bandShift;
    return {
        bottom: at("hand-top") - BESIDE_GAP,
        left: end - (NOTICES_BESIDE_PANEL - m),
        right: end,
        top: top + BESIDE_GAP,
    };
}

/** Clearance at a strip's outer-line limit and around a badge's reserved footprint (px). */
const STRIP_ROOM_GAP = 8;
const STRIP_BADGE_CLEAR = 2;

/** Clearance around the switches' and own row's reserved footprints (px). */
const STRIP_CONTROL_CLEAR = 4;

/** The top strip's melds keep this far above the core and the top badge (px). */
const TOP_CORE_CLEAR = 8;
const TOP_BADGE_CLEAR = 6;

/** Upright, the left badge keeps this far over the core (px). */
const SIDE_BADGE_CORE_GAP = 6;

/**
 * Where an opponent's strips stand and what their rooms end at, by their family's places (px): past the switches, the
 * left strip's line runs on to `end` for a meld shallower than `depth` (none upright); the right strip's line
 * ends at `rightEnd`.
 */
interface StripPlaces {
    readonly origin: number;
    readonly rightEnd: number;
    readonly leftObstacles: readonly StripObstacle[];
    readonly rightObstacles: readonly StripObstacle[];
    readonly leftStart: number;
    readonly leftRoomEnd: number;
    readonly leftPast: { readonly depth: number; readonly end: number } | null;
    readonly topAnchor: number;
    readonly topCap: number | null;
    readonly topStart: number;
    readonly topLane: number;
    readonly topBadgeTop: number;
}

/**
 * The opponents' strips: each one's area sized to its turned footprint (a side strip's deepest reach along its full
 * hand's room, the top one's stacked depth along its line), and the rooms their melds are laid out in.
 */
function opponentStrips(
    { at, frame }: ShellRoom,
    places: StripPlaces,
): Pick<BoardShell, "strips"> & { readonly areas: Record<`strip-${StripSeat}`, BoardRect> } {
    const m = at("m");
    const rw = at("rw");
    const { width } = frame.box;
    const reserve = sideLaneReserve(rw);
    const { leftPast } = places;
    function leftLine(depth: number): number {
        const end =
            leftPast !== null && depth * rw < leftPast.depth
                ? leftPast.end
                : places.leftRoomEnd - STRIP_ROOM_GAP;
        return end - places.leftStart;
    }
    const rightLine = places.origin - places.rightEnd;
    return {
        areas: {
            "strip-left": {
                bottom: places.leftRoomEnd - STRIP_ROOM_GAP,
                left: m,
                right: m + reserve,
                top: places.leftStart,
            },
            "strip-right": {
                bottom: places.origin,
                left: width - m - reserve,
                right: width - m,
                top: m,
            },
            "strip-top": {
                bottom: m + STACKED_DEPTH * rw,
                left: places.topStart,
                right: places.topCap ?? places.topAnchor,
                top: m,
            },
        },
        strips: {
            gap: at("g") + MELD_GAP_EXTRA,
            left: {
                deepLine: leftLine(STACKED_DEPTH),
                line: leftLine(UPRIGHT_DEPTH),
                obstacles: places.leftObstacles,
            },
            right: {
                deepLine: rightLine,
                line: rightLine,
                obstacles: places.rightObstacles,
            },
            rw,
            top: {
                anchor: places.topAnchor,
                badgeDepth: places.topBadgeTop - TOP_BADGE_CLEAR - TILE_EDGE_SHARE * rw - m,
                cap: places.topCap,
                depth: at("core-top") - TOP_CORE_CLEAR - m,
                lane: places.topLane,
                start: places.topStart,
            },
        },
    };
}

/** A side badge's lane ends this far short of a river's reach (px). */
const BADGE_REACH_GAP = 6;

/** A side badge's lane short of a river's reach from its edge, unbounded where it stands clear above that river. */
function laneShortOf(reach: number, from: number, above: boolean): number {
    return above ? Infinity : reach - BADGE_REACH_GAP - from;
}

/**
 * The side badges' widths off an upright board: the left one's lane short of the left river where it stands beside
 * it; the right one a card wide, short of the right river past its clearance (its whole reach where the badge stands
 * beside the river's latest rows) and of the top hand's anchor.
 */
function landscapeBadgeWidths(
    { at, frame, tier }: ShellRoom,
    { rightBadgeTop, sideBadgeTop, sideLane }: LandscapeBadges,
    topAnchor: number,
): [string, number][] {
    const rw = at("rw");
    const badgeX = sideBadgeX(tier, rw);
    const centreTop = at("cy") - at("h");
    const left = laneShortOf(at("reach-left"), badgeX, centreTop - sideBadgeTop - tier.badgeH > 0);
    const rightRiverTop =
        at("cy") + at("h") - ROW_BEFORE_SIDEWAYS * rw - at("rh") - at("latest-drop-gap");
    const besideRiver = rightBadgeTop + tier.badgeH - rightRiverTop > 0;
    const coreRight = at("cx") + at("hx");
    const rightX = frame.box.width - badgeX;
    const right = Math.min(
        tier.sideCardW,
        rightX -
            coreRight -
            Math.max(SIDE_CLEAR, rw) -
            (besideRiver ? at("reach-right") - coreRight : 0),
        rightX - topAnchor - tier.badgeGap,
    );
    return [
        ["left-badge-w", Math.max(0, Math.min(sideLane, left))],
        ["right-badge-w", Math.max(0, right)],
    ];
}

/** The river's clearance a badge's lane keeps: half a river tile, never under `RIVER_CLEAR_MIN`. */
function riverClear(rw: number): number {
    return Math.max(RIVER_CLEAR_MIN, rw / 2);
}

/**
 * Off an upright board, the top hand's full reach stands centred, moved right as far as its badge's lane under its
 * start needs, short of the board's edge; the lane runs from past the top river to there, the line from the margin.
 */
function landscapeTop(room: ShellRoom): Pick<StripPlaces, "topAnchor" | "topLane" | "topStart"> {
    const { at, frame, tier } = room;
    const m = at("m");
    const reach = fullReach(at("rw"), "top");
    const clear = riverClear(at("rw"));
    const start = m;
    const badgeRight = frame.box.width - m - tier.badgeGap;
    const pastRiver = at("cx") + at("hx") + clear;
    const centred = Math.max(at("cx") + reach / 2, pastRiver + tier.sideLaneMin);
    const anchor = Math.max(start + reach, Math.min(centred, badgeRight));
    return {
        topAnchor: anchor,
        topLane: Math.min(tier.sideCardW, anchor - pastRiver),
        topStart: start,
    };
}

/**
 * A desktop's right hand's origin, from its full reach: up from the band, else from the top margin across it, and
 * centred on the core as far as that allows; the cog stands over whatever reaches under it.
 */
function desktopRightOrigin({ at }: ShellRoom, fromBand: number): number {
    const reach = sideStripReach(at("rw"));
    const top = at("m") + reach;
    return Math.min(Math.max(fromBand, top), Math.max(top, at("cy") + reach / 2));
}

/** A phone's right hand's origin, from its family's lengths. */
function phoneRightOrigin({ at, tier }: ShellRoom): number {
    const room = phoneRightRoom({
        ...tier,
        cy: at("cy"),
        handTop: at("hand-top"),
        ownMeldRise: at("own-meld-rise"),
        rw: at("rw"),
    });
    return phoneRightHand(room).origin;
}

/**
 * A phone's or a desktop's slots: the corner at the top right, inside the right strip; the switches at
 * the band's start, stepped in past the left hand where its reach meets them; the decisions' place after them (a
 * phone's beside the right river under the right badge); the notices' field past the left strip's deepest reach,
 * under the badges and the top river, short of the left river and the band (a phone's over a panel under the right
 * strip's end); the own row.
 */
function landscapeShell(room: ShellRoom): BoardShell {
    const { at, frame, tier } = room;
    const { box, chrome, family } = frame;
    const { height, width } = box;
    const phone = family === "phone";
    const m = at("m");
    const handTop = at("hand-top");
    const rowRise = at("row-rise");
    const bandTop = handTop - at("band-gap") - at("control-h") - rowRise - at("band-lift");
    const rowBottom = at("band-bottom") - rowRise;
    const switchesTop = at("switches-bottom") - switchesPlace(tier);
    const left = landscapeLeft(room, { bandTop, switchesTop });
    const switchesRight = left.switchesLeft + rowWidth(SWITCH_CHIPS, tier.switchH, tier.chipGap);
    const badges = landscapeBadges(room, rowBottom);
    const { badgeH } = tier;
    const ownStart = Math.max(m, (width - at("own-inline") - FULL_HAND * at("ow")) / 2);
    const ownLead = ownStart + at("own-inline");
    const own = ownLane(room, {
        ownLead,
        plateReach: chrome === "small" ? Infinity : switchesRight,
    });
    const actions = phone
        ? {
              bottom: rowBottom,
              left: at("reach-right") + ACTIONS_GAP,
              right: width - m,
              top: badges.rightBadgeTop + badgeH + ACTIONS_GAP,
          }
        : desktopActions(room, {
              badgeEnd: own.end,
              handRight: ownLead + FULL_HAND * at("ow"),
              rowBottom,
              switchesRight,
          });
    const foregroundTop = bandTop - at("band-gap");
    const origin = phone
        ? phoneRightOrigin(room)
        : desktopRightOrigin(room, foregroundTop + RIGHT_FROM_BAND_GAP);
    const top = landscapeTop(room);
    const badgeWidths = landscapeBadgeWidths(room, badges, top.topAnchor);
    const strips = opponentStrips(room, {
        ...top,
        leftObstacles: [
            {
                depth: sideBadgeX(tier, at("rw")) - m - STRIP_BADGE_CLEAR,
                from: badges.sideBadgeTop - left.leftStart - STRIP_BADGE_CLEAR,
                to: badges.sideBadgeTop + badgeH - left.leftStart + STRIP_BADGE_CLEAR,
            },
            {
                depth: left.switchesLeft - m - STRIP_CONTROL_CLEAR,
                from: switchesTop - left.leftStart - STRIP_CONTROL_CLEAR,
                to: at("switches-bottom") - left.leftStart + STRIP_CONTROL_CLEAR,
            },
            {
                depth: ownStart - m - STEP_IN_GAP,
                from: bandTop - left.leftStart,
                to: height - left.leftStart,
            },
        ],
        leftPast: {
            depth: Math.min(left.switchesLeft, ownStart - STEP_IN_GAP) - m,
            end: height - m,
        },
        leftRoomEnd: left.leftRoomEnd,
        leftStart: left.leftStart,
        origin,
        rightEnd: m,
        rightObstacles: [
            {
                depth: sideBadgeX(tier, at("rw")) - m - STRIP_BADGE_CLEAR,
                from: origin - badges.rightBadgeTop - badgeH - STRIP_BADGE_CLEAR,
                to: origin - badges.rightBadgeTop + STRIP_BADGE_CLEAR,
            },
        ],
        topBadgeTop: badges.topBadgeTop,
        topCap: null,
    });
    const fieldGap = FIELD_GAP[phone ? "phone" : chrome];
    const field = {
        bottom: Math.min(bandTop, switchesTop) - (phone ? PHONE_FIELD_BAND_GAP : FIELD_BAND_GAP),
        left:
            m +
            (family === "desktop" && chrome === "small" ? 0 : sideLaneReserve(at("rw"))) +
            fieldGap,
        right: at("reach-left") - FIELD_RIVER_GAP,
        top: Math.max(badges.sideBadgeTop + badgeH + fieldGap, at("reach-top-row3") + fieldGap),
    };
    const beside = phone
        ? besideField(room, {
              bandShift: at("band-shift"),
              foregroundTop,
              origin,
          })
        : field;
    const cornerRight = strips.areas["strip-right"].left - STRIP_ROOM_GAP;
    const cornerTop =
        cornerRight - menuSize(at("rw")) >= strips.areas["strip-top"].right + STRIP_ROOM_GAP
            ? m
            : Math.max(strips.areas["strip-top"].bottom, badges.topBadgeTop + badgeH) +
              STRIP_ROOM_GAP;
    return {
        areas: {
            actions,
            corner: {
                bottom: height,
                left: 0,
                right: cornerRight,
                top: cornerTop,
            },
            field,
            "field-beside": beside,
            hand: {
                bottom: handTop + at("oh"),
                left: ownLead,
                right: width - m,
                top: handTop,
            },
            ...strips.areas,
            switches: {
                bottom: at("switches-bottom"),
                left: left.switchesLeft,
                right: width,
                top: 0,
            },
        },
        lengths: [
            ...badgeWidths,
            ["actions-bottom", actions.bottom],
            ["actions-left", actions.left],
            ["actions-right", width - actions.right],
            ["counters-top", countersTop(tier, at("rw"), badges.sideBadgeTop)],
            ["field-beside-height", Math.max(0, beside.bottom - beside.top)],
            ["field-height", Math.max(0, field.bottom - field.top)],
            ["foreground-top", foregroundTop],
            ["own-badge-x", ownLead],
            ["own-lane", own.lane],
            ["own-row-lead", 0],
            ["own-row-w", width - m - ownLead],
            ["own-start", ownStart],
            ["right-badge-top", badges.rightBadgeTop],
            ["side-badge-top", badges.sideBadgeTop],
            ["side-badge-x", sideBadgeX(tier, at("rw"))],
            ["switches-left", left.switchesLeft],
            ["switches-right", switchesRight],
            ["top-badge-top", badges.topBadgeTop],
            ["top-lane", top.topLane],
            ["top-strip-x", top.topAnchor],
        ],
        strips: strips.strips,
    };
}

/**
 * An upright board's slots: the corner; the decisions' rows across the board
 * short of the right strip's deepest reach; the notices' field under the bottom river over those rows (over a panel
 * under the right strip's end); the own row across the board; the switches at the decision row's left end.
 */
function uprightShell(room: ShellRoom): BoardShell {
    const { at, frame, tier } = room;
    const { height, width } = frame.box;
    const m = at("m");
    const rw = at("rw");
    const handTop = at("hand-top");
    const reach = sideStripReach(rw);
    const foregroundTop = handTop - 2 * at("band-gap") - at("control-h");
    const bandTop = foregroundTop + at("band-gap");
    const topBadgeTop = belowTopStrip(m, rw);
    const lowestTop = topBadgeTop + tier.pillH + UPRIGHT_PILL_GAP + tier.badgeH + UPRIGHT_BADGE_GAP;
    const origin = Math.min(
        foregroundTop + RIGHT_FROM_BAND_GAP,
        Math.max(at("cy") + reach / 2, lowestTop + reach),
    );
    const bandShift = origin - bandTop - HALF_PIXEL > 0 ? at("rh") + STEP_IN_GAP : 0;
    const strip = m + sideLaneReserve(rw) + UPRIGHT_STRIP_GAP;
    const switchesRight = m + rowWidth(SWITCH_CHIPS, tier.switchH, tier.chipGap);
    const switchesTop = at("actions-bottom") - tier.switchH;
    const leftRoomEnd =
        frame.slots.band === "play"
            ? Math.min(bandTop, switchesTop - STRIP_CONTROL_CLEAR)
            : bandTop;
    const actionsLeft = frame.slots.band === "play" ? switchesRight + tier.bandGap : m;
    const actionsRight =
        frame.slots.band === "play"
            ? Math.max(m, Math.min(strip, width - actionsLeft - ACTIONS_ROW_MIN))
            : strip;
    const bottomRiverEnd =
        at("cy") + at("h") + at("g") + RIVER_ROWS_RUN_ON * at("rh") + at("latest-drop-gap");
    const field = {
        bottom: at("notices-bottom"),
        left: m + sideLaneReserve(rw) + FIELD_GAP.phone,
        right: width - strip,
        top: bottomRiverEnd + FIELD_GAP.phone,
    };
    const beside = besideField(room, { bandShift, foregroundTop, origin });
    const sideStart = sidesStart(tier, rw);
    const leftStart = Math.max(
        topBadgeTop,
        Math.min(at("cy") - reach / 2, leftRoomEnd - LEFT_HAND_GAP - reach),
    );
    const sideBadgeTop = Math.max(
        sideStart,
        Math.min(leftStart, at("core-top") - tier.badgeH - SIDE_BADGE_CORE_GAP),
    );
    const rightBadgeTop = origin - reach - UPRIGHT_BADGE_GAP - tier.badgeH;
    const badgeX = sideBadgeX(tier, rw);
    const sideLane = Math.min(tier.sideCardW, at("cx") - at("hx") - riverClear(rw) - badgeX);
    const sideBottom = sideBadgeTop + tier.badgeH;
    const laneOverCore = laneShortOf(at("reach-top-left"), badgeX, at("core-top") - sideBottom > 0);
    const laneByRiver = laneShortOf(at("reach-left"), badgeX, at("cy") - at("h") - sideBottom > 0);
    const leftBadgeW = Math.min(
        tier.sideCardW,
        Math.max(tier.sideLaneMin, laneOverCore),
        laneByRiver,
    );
    const topAnchor = Math.max(m + reach, at("cx") + reach / 2);
    const ownStart = (width - FULL_HAND * at("ow")) / 2;
    const counters = countersTop(tier, rw, sideBadgeTop);
    const levelCounters = counters < topBadgeTop + tier.badgeH;
    const laneStart = badgeX + (levelCounters ? tier.countersW + tier.badgeGap : 0);
    const topLane = Math.min(tier.sideCardW, topAnchor - laneStart);
    const strips = opponentStrips(room, {
        leftObstacles: [
            {
                depth: badgeX - m - STRIP_BADGE_CLEAR,
                from: sideBadgeTop - leftStart - STRIP_BADGE_CLEAR,
                to: sideBadgeTop + tier.badgeH - leftStart + STRIP_BADGE_CLEAR,
            },
            {
                depth: ownStart - m - STEP_IN_GAP,
                from: handTop - at("own-rise") - leftStart - STRIP_CONTROL_CLEAR,
                to: height - leftStart,
            },
        ],
        leftPast: null,
        leftRoomEnd,
        leftStart,
        origin,
        rightEnd: m + STACKED_DEPTH * rw + STRIP_ROOM_GAP,
        rightObstacles: [
            {
                depth: badgeX - m - STRIP_BADGE_CLEAR,
                from: origin - rightBadgeTop - tier.badgeH - STRIP_BADGE_CLEAR,
                to: origin - rightBadgeTop + STRIP_BADGE_CLEAR,
            },
        ],
        topAnchor,
        topBadgeTop,
        topCap: width - m,
        topLane,
        topStart: m,
    });
    return {
        areas: {
            actions: {
                bottom: at("actions-bottom"),
                left: actionsLeft,
                right: width - actionsRight,
                top: 0,
            },
            corner: {
                bottom: height,
                left: 0,
                right: width - m,
                top: m,
            },
            field,
            "field-beside": beside,
            hand: {
                bottom: handTop + at("oh"),
                left: m,
                right: width - m,
                top: handTop,
            },
            ...strips.areas,
            switches: {
                bottom: at("actions-bottom"),
                left: m,
                right: switchesRight,
                top: switchesTop,
            },
        },
        lengths: [
            ["actions-left", actionsLeft],
            ["actions-right", actionsRight],
            ["upright-upper-clear", strip - actionsRight],
            ["upright-upper-width", width - strip - m],
            ["counters-top", counters],
            ["field-beside-height", Math.max(0, beside.bottom - beside.top)],
            ["field-height", Math.max(0, field.bottom - field.top)],
            ["foreground-top", foregroundTop],
            ["own-badge-x", ownStart],
            ["own-row-lead", ownStart - m],
            ["own-row-w", width - m - ownStart],
            ["own-start", ownStart],
            ["right-badge-top", rightBadgeTop],
            ["side-badge-top", sideBadgeTop],
            ["left-badge-w", Math.max(0, leftBadgeW)],
            ["right-badge-w", sideLane],
            ["side-badge-x", badgeX],
            ["top-badge-top", topBadgeTop],
            ["top-lane", topLane],
            ["top-strip-x", topAnchor],
        ],
        strips: strips.strips,
    };
}

/**
 * What every family's board reads alike: an opponent's hand's gaps and full reach, a side strip's stacked depth and
 * reserved lane, the face floor.
 */
function stripFacts(rw: number): [string, number][] {
    return [
        ["bgap", hairline(rw)],
        ["dg", drawnGap(rw, "top")],
        ["side-dg", drawnGap(rw, "left")],
        ["face-floor", FACE_FLOOR],
        ["full-reach", fullReach(rw, "left")],
        ["strip-depth", STACKED_DEPTH * rw],
        ["strip-reserve", sideLaneReserve(rw)],
    ];
}

/** A family's slots from its lengths. */
function boardShell(frame: BoardFrame, lengths: BoardLengths): BoardShell {
    function at(name: string): number {
        return lengths[name] ?? 0;
    }
    const shell =
        frame.family === "upright"
            ? uprightShell({
                  at,
                  frame,
                  tier: { ...DESKTOP_CHROME[frame.chrome], ...UPRIGHT_CHROME },
              })
            : landscapeShell({
                  at,
                  frame,
                  tier:
                      frame.family === "phone"
                          ? phoneChrome(at("rw"))
                          : DESKTOP_CHROME[frame.chrome],
              });
    return { ...shell, lengths: [...shell.lengths, ...stripFacts(at("rw"))] };
}

/** A named edge of a slot's area, on a line of its own after any other at its place where its area is empty. */
type GridEdge = readonly [name: string, at: number, after: boolean];

/** A line of a grid template: where it stands, whether past the line there, and the edges it names. */
interface GridLine {
    readonly at: number;
    readonly after: boolean;
    readonly names: readonly string[];
}

/** A grid template whose lines stand at each named edge and the board's edges, merged where edges meet. */
function lineTemplate(edges: readonly GridEdge[], extent: number): string {
    const lines = new Map<string, GridLine>([
        ["0:false", { after: false, at: 0, names: [] }],
        [`${extent}:false`, { after: false, at: extent, names: [] }],
    ]);
    for (const [name, at, after] of edges) {
        const key = `${at}:${after}`;
        lines.set(key, { after, at, names: [...(lines.get(key)?.names ?? []), name] });
    }
    const sorted = [...lines.values()].toSorted(
        (first, second) => first.at - second.at || Number(first.after) - Number(second.after),
    );
    return sorted
        .map(({ at, names }, index) => {
            const label = names.length > 0 ? `[${names.join(" ")}]` : "";
            const next = sorted[index + 1];
            return next === undefined ? label : `${label} ${next.at - at}px`;
        })
        .join(" ")
        .trim();
}

/** A slot's edges along one axis within the board: an empty or inverted area keeps its end on a line past its start. */
function axisEdges(
    name: string,
    [start, end]: readonly [number, number],
    extent: number,
): GridEdge[] {
    const from = Math.min(extent, Math.max(0, start));
    const to = Math.min(extent, Math.max(from, end));
    return [
        [`${name}-start`, from, false],
        [`${name}-end`, to, to === from],
    ];
}

/** The shell's grid: a line at every slot's edges. */
function shellTracks(
    areas: Readonly<Record<string, BoardRect>>,
    { height, width }: BoardBox,
): BoardTracks {
    const rects = Object.entries(areas);
    return {
        columns: lineTemplate(
            rects.flatMap(([name, rect]) => axisEdges(name, [rect.left, rect.right], width)),
            width,
        ),
        rows: lineTemplate(
            rects.flatMap(([name, rect]) => axisEdges(name, [rect.top, rect.bottom], height)),
            height,
        ),
    };
}

function familyLengths(frame: BoardFrame): BoardLengths {
    if (frame.family === "phone") {
        return phoneLengths(frame);
    }
    if (frame.family === "upright") {
        return uprightLengths(frame);
    }
    return desktopLengths(frame);
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
    const frame = { box: settled, chrome, family, slots: input.slots };
    const sizes = sized ? familyLengths(frame) : {};
    const shell = sized ? boardShell(frame, sizes) : null;
    return Object.freeze({
        box: Object.freeze(settled),
        chrome,
        family,
        gutter: phone ? 0 : PAGE_GUTTER,
        lengths: Object.freeze({
            ...sizes,
            ...Object.fromEntries(shell?.lengths ?? []),
        }),
        strips: shell === null ? null : Object.freeze(shell.strips),
        tracks: Object.freeze(
            shell === null ? { columns: "", rows: "" } : shellTracks(shell.areas, settled),
        ),
    });
}

export { boardGeometry, shellTracks };
export type {
    BoardBox,
    BoardEdges,
    BoardFamily,
    BoardGeometry,
    BoardInput,
    BoardLengths,
    BoardRect,
    BoardSlots,
    BoardTracks,
};
