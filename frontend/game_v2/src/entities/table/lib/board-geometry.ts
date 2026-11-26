import { LYING_BODY, RIVER_ROWS, RIVER_ROW_SIZE, STANDING_OVERHANG } from "@/entities/tile";

import {
    BAR_MIN,
    CORE_TILES,
    type ChromeTier,
    DESKTOP_CENTRE_TILES,
    DESKTOP_RIVER_GAP_SHARE,
    FACE_FLOOR,
    FULL_HAND,
    LARGE_CHROME_HEIGHT,
    LARGE_CHROME_WIDTH,
    LATEST_DISCARD_GAP,
    LATEST_GAP_RIVER_TILE,
    LYING_X_SHARE,
    LYING_Y_SHARE,
    MELD_GAP_EXTRA,
    MELD_GAP_TIGHT,
    MENU_MAX,
    MENU_MIN,
    MENU_RIVER_SHARE,
    OWN_BY_RIVER_LEAST,
    OWN_BY_RIVER_OFF_PHONE,
    OWN_BY_RIVER_WANTED,
    OWN_MELD_SCALE,
    OWN_ROW_GAP,
    PAGE_GUTTER,
    PHONE_CENTRE_MIN_HEIGHT,
    PHONE_CENTRE_MIN_WIDTH,
    PHONE_CHROME,
    PHONE_CHROME_RIVER,
    PHONE_FELT_BY_HEIGHT,
    PHONE_HEIGHT,
    PHONE_LATEST_GAP_MIN,
    PHONE_OWN_FLOOR,
    PHONE_OWN_GIVEN_FOR_RIVER,
    PHONE_OWN_TAP_FLOOR,
    type PhoneChrome,
    REGULAR_CHROME_HEIGHT,
    RIVER_CORNER_CLEAR,
    RIVER_GAP_SHARE,
    ROWS_BEFORE_RUN_ON,
    RUN_ON_REACH_TILES,
    SIDEWAYS_UNITS,
    SIDE_EDGE_SHARE,
    SIDE_LANE_GAP,
    SIDE_REACH_TILES,
    SMALL_CHROME_WIDTH,
    STACKED_DEPTH,
    TABLE_COLUMN_TILES,
    TIER_CHROME,
    TILE_ASPECT,
    TILE_EDGE_SHARE,
    TOP_CORE_CLEAR,
    TOP_HAND_AIR,
    TOP_HAND_BACK_EDGE_SHARE,
    TOP_HAND_EDGE_SHARE,
    TOP_HAND_GAP,
    type TierChrome,
    UPRIGHT_DEPTH,
} from "./board-constants";
import {
    type MeldShape,
    type StripRooms,
    type StripSeat,
    drawnGap,
    ownMeldTile as fitOwnMelds,
    handLength,
} from "./strip-layout";

type BoardFamily = "phone" | "desktop";

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
    readonly decisionCapacity?: number;
}

/** The board's box as measured, the page's raw safe-area insets, the edges the page applies around the box now (px), and its slots. */
interface BoardInput {
    readonly box: BoardBox;
    readonly safeInsets: BoardEdges;
    readonly appliedEdges: BoardEdges;
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
    readonly switches: SwitchesForm;
    readonly replay: ReplayForm;
    readonly areas: Readonly<Partial<Record<string, BoardRect>>>;
    /** Where a desktop's controls stand (`DesktopArrangement`); null for a phone or an unsized board. */
    readonly arrangement: DesktopArrangement | null;
}

/** The switches step in this far past an opponent's tile height (px). */
const STEP_IN_GAP = 6;

/** The play switches' strip: three square chips and the names' button. */
const SWITCH_CHIPS = 4;

/** The play switches where they show their whole names, with no names' button. */
const LABELLED_SWITCHES = 3;

/** The replay's moves in the switches' place. */
const REPLAY_MOVES = 7;
/** The replay's options at the band's end: the viewpoint, the round list and the tools. */
const REPLAY_OPTIONS = 3;

/** An opponent's full hand's tiles. */
const HAND_TILES = 14;

/**
 * A desktop's vertical stack in river tiles, past the latest discards' gaps across the light: the top hand and its edge,
 * a gap, the core (a top and bottom river's rows with their edges in the latest discards' gaps, around the centre, the
 * top river's gap past the edge its rows drop toward the centre), a gap, the own melds' rise and the own row with its
 * edge. Its px are a little under this, their roundings down.
 */
const DESKTOP_STACK_TILES =
    TILE_ASPECT +
    TOP_HAND_BACK_EDGE_SHARE +
    TOP_HAND_GAP +
    CORE_TILES +
    2 * (DESKTOP_RIVER_GAP_SHARE - RIVER_GAP_SHARE) +
    3 * TILE_EDGE_SHARE +
    DESKTOP_CENTRE_TILES +
    OWN_ROW_GAP +
    Math.max(
        0,
        STACKED_DEPTH * LYING_Y_SHARE * OWN_MELD_SCALE - OWN_BY_RIVER_OFF_PHONE * TILE_ASPECT,
    ) +
    OWN_BY_RIVER_OFF_PHONE * TILE_ASPECT +
    Math.max(OWN_BY_RIVER_OFF_PHONE * STANDING_OVERHANG, OWN_MELD_SCALE * TILE_EDGE_SHARE);

/**
 * The latest discard's reserve along the light off a phone (px): the gap and a tile edge, deeper than the painted lip
 * (`latestLip`) its move clears where it borders an earlier body, the rest kept as margin.
 */
function latestDropGap(rw: number): number {
    return LATEST_DISCARD_GAP + Math.round(TILE_EDGE_SHARE * rw);
}

/** A lying river tile's painted edge past its slot (px), which the latest discard clears where it borders a body. */
function latestLip(rw: number): number {
    return Math.round(LYING_BODY.edge * rw);
}

/** A phone's latest discard's gap from its neighbours (px): the desktop gap scaled to its river tile. */
function phoneLatestGap(rw: number): number {
    return Math.max(
        PHONE_LATEST_GAP_MIN,
        Math.round((LATEST_DISCARD_GAP * rw) / LATEST_GAP_RIVER_TILE),
    );
}

/**
 * A phone's reserve for its latest discard's longest move off its slot (px): its gap and the lip it clears, never under
 * the desktop gap, which a small phone's river already spares.
 */
function phoneLatestDrop(rw: number): number {
    return Math.max(LATEST_DISCARD_GAP, phoneLatestGap(rw) + latestLip(rw));
}

/** A phone replay's moves: the five past the round's ends. */
const REPLAY_MOVES_ON_PHONE = 5;

/** The furiten mark's reserve, its gap to what it stands past and its height (px). */
const FURITEN_RESERVE = 88;
const FURITEN_GAP = 8;
const FURITEN_H = 18;

/** No phone's river tile passes this share of its height, nor goes under `PHONE_SMALLEST_RIVER` (px). */
const PHONE_MAX_RIVER_SHARE = 10;
const PHONE_SMALLEST_RIVER = 2;

/** A panel keeps this far off the board's edges where nothing else is reserved there (px). */
const PANEL_GAP = 8;

function classifyFamily({ height }: BoardBox): BoardFamily {
    return height < PHONE_HEIGHT ? "phone" : "desktop";
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

/**
 * How far a box's chrome stands from the regular record to the large one, within 0..1: the lesser of its width's share
 * of the way from `SMALL_CHROME_WIDTH` to `LARGE_CHROME_WIDTH` and its height's from `REGULAR_CHROME_HEIGHT` to
 * `LARGE_CHROME_HEIGHT`.
 */
function chromeShare({ width, height }: BoardBox): number {
    const across = (width - SMALL_CHROME_WIDTH) / (LARGE_CHROME_WIDTH - SMALL_CHROME_WIDTH);
    const down = (height - REGULAR_CHROME_HEIGHT) / (LARGE_CHROME_HEIGHT - REGULAR_CHROME_HEIGHT);
    return Math.min(1, Math.max(0, Math.min(across, down)));
}

/** A tier's chrome px: the small record, or past it each field from the regular record to the large one by `share`. */
function tierChrome(chrome: ChromeTier, share: number): TierChrome {
    if (chrome === "small") {
        return TIER_CHROME.small;
    }
    const { large, regular } = TIER_CHROME;
    return mapChrome(regular, (field) => regular[field] + (large[field] - regular[field]) * share);
}

/** The river tile of a desktop board as tall as the large record, past which a large board's chrome grows with it. */
const LARGE_RIVER = Math.floor(LARGE_CHROME_HEIGHT / DESKTOP_STACK_TILES);

/** How far a board's chrome grows past its tier's px: a large one's with its river tile past `LARGE_RIVER`. */
function chromeGrowth(chrome: ChromeTier, rw: number): number {
    return chrome === "large" ? Math.max(1, rw / LARGE_RIVER) : 1;
}

/** A tier's chrome px grown by `growth`. */
function grownChrome(tier: TierChrome, growth: number): TierChrome {
    return mapChrome(tier, (field) => tier[field] * growth);
}

/** `tier` with its every field `at`'s. */
function mapChrome(tier: TierChrome, at: (field: keyof TierChrome) => number): TierChrome {
    const mapped: Record<keyof TierChrome, number> = { ...tier };
    for (const field of Object.keys(tier).filter((key): key is keyof TierChrome => key in tier)) {
        mapped[field] = at(field);
    }
    return mapped;
}

/** A row of controls this many and this large, this far apart. */
function rowWidth(count: number, size: number, gap: number): number {
    return count * size + (count - 1) * gap;
}

/** An opponent's full hand along its line. */
function fullReach(rw: number, seat: StripSeat): number {
    return handLength({ drawn: true, rw, seat, tiles: HAND_TILES });
}

/** The most open kans a side strip reserves a line for, at the meld face floor. */
const RESERVED_KANS = [1, 2, 3, 4] as const;

/** The open melds a phone's right strip always holds on its line: a seat's ordinary three pons. */
const ORDINARY_PONS = 3;

/**
 * A side hand with `count` open melds of `upright` tiles at the face floor beside its remaining tiles, `gap` apart, along
 * its line (px).
 */
function meldsReach(rw: number, { count, floor, gap, share, upright }: MeldsLine): number {
    return (
        handLength({ drawn: true, rw, seat: "left", tiles: HAND_TILES - 3 * count }) +
        count * (gap + (upright + SIDEWAYS_UNITS) * share * (floor ?? FACE_FLOOR))
    );
}

interface MeldsLine {
    readonly count: number;
    readonly floor?: number;
    readonly upright: number;
    readonly gap: number;
    readonly share: number;
}

function kansReach(
    rw: number,
    count: number,
    line: Omit<MeldsLine, "count" | "gap" | "upright">,
): number {
    return meldsReach(rw, { ...line, count, gap: riverGap(rw) + MELD_GAP_EXTRA, upright: 3 });
}

function ponsReach(rw: number, floor?: number): number {
    return meldsReach(rw, {
        count: ORDINARY_PONS,
        floor,
        gap: riverGap(rw) + MELD_GAP_EXTRA,
        share: LYING_Y_SHARE,
        upright: 2,
    });
}

/**
 * A phone's side lanes stand above its own row where their lines hold this many open kans at the face floor, their gaps
 * closed to the tightest, reaching at most into the own row's clearance; a rarer fourth lies on past the line.
 */
const PHONE_LINE_KANS = 3;

function tightKansReach(rw: number, floor?: number): number {
    return meldsReach(rw, {
        count: PHONE_LINE_KANS,
        floor,
        gap: MELD_GAP_TIGHT,
        share: LYING_Y_SHARE,
        upright: 3,
    });
}

/** A side strip reserves one line even for four open kans at the meld face floor. */
function sideStripReach(rw: number, floor?: number): number {
    return kansLineReach(rw, { floor, share: LYING_Y_SHARE });
}

function kansLineReach(rw: number, line: Omit<MeldsLine, "count" | "gap" | "upright">): number {
    return Math.max(
        fullReach(rw, "left"),
        ...RESERVED_KANS.map((count) => kansReach(rw, count, line)),
    );
}

/**
 * A phone's side strip reserves its full concealed hand and as much of a four-kan line at the face floor as `room` holds
 * (a browser's bars leave a box too short for all of it): the melds of a rarer denser seat lie on past the line
 * (`stripLayout`'s overflow), never shrinking the river tile for them.
 */
function phoneSideReach(rw: number, room: number, floor?: number): number {
    return Math.max(fullReach(rw, "left"), Math.min(sideStripReach(rw, floor), room));
}

/**
 * Where a side strip's line ends: `clear` above the own row and the rise its melds take (a desktop's left strip
 * `STRIP_ROOM_GAP`, a phone's both `phoneRowTop`'s).
 */
function sideLineEnd(handTop: number, ownMeldRise: number, clear: number): number {
    return handTop - ownMeldRise - clear;
}

/**
 * Where a phone's side strips' lines end above its own row, which runs on under their lanes: `STRIP_CONTROL_CLEAR` past
 * the edge their last tile shows below its slot, so neither strip's foot nor the left one's drawn tile or far meld
 * touches the own hand.
 */
function phoneRowTop(at: Readonly<Record<"handTop" | "ownMeldRise" | "rw", number>>): number {
    return sideLineEnd(
        at.handTop,
        at.ownMeldRise,
        STRIP_CONTROL_CLEAR + Math.ceil(SIDE_EDGE_SHARE * at.rw),
    );
}

/** A side strip's lane at the table column's edge: its stacked depth and a clearance. */
function sideLane(rw: number): number {
    return STACKED_DEPTH * rw + SIDE_LANE_GAP;
}

/**
 * A desktop's table, centred: the own row of a full hand at the own tile between the side strips' lanes, never narrower
 * than `narrowestColumn`: its edges (px).
 */
function desktopTable({
    gap,
    ow,
    rw,
    width,
}: Readonly<Record<"gap" | "ow" | "rw" | "width", number>>): Readonly<
    Record<"left" | "right", number>
> {
    const across = Math.max(narrowestColumn(rw, gap), FULL_HAND * ow + 2 * sideLane(rw));
    const left = (width - across) / 2;
    return { left, right: left + across };
}

/**
 * A desktop's own tile at a river tile: as large as a full hand between the side strips' lanes holds within the width
 * the bars leave (`bar` each), at most `OWN_BY_RIVER_OFF_PHONE` river tiles (px).
 */
function desktopOwnTile({
    bar,
    rw,
    width,
}: Readonly<Record<"bar" | "rw" | "width", number>>): number {
    const room = width - 2 * bar - 2 * sideLane(rw);
    return Math.min(Math.floor(OWN_BY_RIVER_OFF_PHONE * rw), Math.floor(room / FULL_HAND));
}

/**
 * The narrowest desktop table: the core across (the side rivers' four rows and their latest discards' gaps) and
 * a side lane and a strip's room gap on each side (px).
 */
function narrowestColumn(rw: number, gap: number): number {
    return RIVER_ROW_SIZE * rw + 2 * (sideRiverReach(rw, gap) + sideLane(rw) + STRIP_ROOM_GAP);
}

/** A side river's reach from the centre: the gap, its rows and the latest discard's gap (px). */
function sideRiverReach(rw: number, gap: number): number {
    return gap + (SIDE_REACH_TILES / 2) * rw + LATEST_DISCARD_GAP;
}

/** The gap between the centre and a river, a whole pixel. */
function riverGap(rw: number): number {
    return Math.round(RIVER_GAP_SHARE * rw);
}

/** A desktop's gap between the centre and a river, a whole pixel. */
function desktopRiverGap(rw: number): number {
    return Math.round(DESKTOP_RIVER_GAP_SHARE * rw);
}

/** A top or bottom river's reach from the centre at its capacity: the gap and its rows. */
function rightRiverLift(rw: number, gap: number): number {
    return Math.max(0, Math.round(TILE_EDGE_SHARE * rw) - gap + RIVER_CORNER_CLEAR);
}

function riverRows(rw: number, gap: number): number {
    return gap + (CORE_TILES / 2 - RIVER_GAP_SHARE) * rw;
}

const COMPASS_SLOT_PADDING = 3;
const COMPASS_DORA_GAP = 6;
const COMPASS_DORA_SCALE = 0.9;
const COMPASS_HEIGHT_FLOOR = 48;

/**
 * The core's lengths: the centre (`cx`/`cy` its middle, `c`/`h` its height and half, `w`/`hx` its width and half), the
 * river tile, the gaps between the centre and the rivers (the top one's `g-top`), and the rivers' reserved reach, a
 * row's sideways riichi tile and the latest discard's gap counted: a side river's fourth row, a top or bottom river's
 * third row run on to eight tiles, and the top river's third row's centre-facing edge, which no gap moves toward the
 * centre; the latest discard's gaps; and how far the right river stands above the centre's foot (`rightLift`), so its
 * first tile's edge keeps off a bottom row a sideways tile runs past the centre's corner.
 */
function coreLengths(
    {
        cx,
        cy,
        height,
        rw,
        width,
    }: Readonly<Record<"cx" | "cy" | "height" | "rw" | "width", number>>,
    {
        drop,
        gap,
        latestGap,
        rightLift,
        topGap,
    }: Readonly<Record<"drop" | "gap" | "latestGap" | "rightLift" | "topGap", number>>,
): [string, number][] {
    const slotWidth = width / RIVER_ROW_SIZE;
    const slotHeight = slotWidth * (TILE_ASPECT * LYING_Y_SHARE + LYING_BODY.edge);
    const panelRoom = height - slotHeight - COMPASS_SLOT_PADDING;
    const panelHeight = Math.max(COMPASS_HEIGHT_FLOOR, panelRoom);
    const indicatorRow = slotHeight * COMPASS_DORA_SCALE + COMPASS_DORA_GAP;
    const compassMid = cy + (gap - topGap + rw * LYING_BODY.edge) / 2;
    const hx = width / 2;
    const sideReach = (SIDE_REACH_TILES / 2) * rw + latestGap;
    const runOnReach = RUN_ON_REACH_TILES * rw + latestGap;
    return [
        ["c", height],
        ["compass-dora-width", slotWidth * COMPASS_DORA_SCALE],
        ["compass-dora-row", indicatorRow],
        ["compass-inset", (panelRoom - panelHeight) / 2],
        ["compass-panel-height", panelHeight],
        ["compass-top", compassMid - (indicatorRow + panelHeight) / 2],
        ["cx", cx],
        ["cy", cy],
        ["g", gap],
        ["g-top", topGap],
        ["h", height / 2],
        ["hx", hx],
        ["latest-discard-gap", latestGap],
        ["latest-drop-gap", drop],
        ["latest-lip", latestLip(rw)],
        ["reach-bottom-right", cx - hx + runOnReach],
        ["reach-left", cx - hx - gap - (SIDE_REACH_TILES / 2) * rw - latestGap],
        ["reach-right", cx + hx + gap + sideReach],
        ["reach-top-left", cx + hx - runOnReach],
        ["reach-top-row3", cy - height / 2 - topGap - ROWS_BEFORE_RUN_ON * rw],
        ["rh", rw * TILE_ASPECT],
        ["river-across", RIVER_ROWS["run-on"] * rw * TILE_ASPECT * LYING_Y_SHARE],
        ["river-along", RIVER_ROW_SIZE * rw * LYING_X_SHARE],
        ["river-right-lift", rightLift],
        ["rw", rw],
        ["side-river-across", RIVER_ROWS["run-on"] * rw * TILE_ASPECT * LYING_X_SHARE],
        ["side-river-along", RIVER_ROW_SIZE * rw * LYING_Y_SHARE],
        ["w", width],
    ];
}

/** The page's cog's side, from the river tile within its floor and cap. */
function menuSize(rw: number, cap = MENU_MAX): number {
    return Math.min(cap, Math.max(MENU_MIN, MENU_RIVER_SHARE * rw));
}

/** The cog's side, its cap grown with the chrome; it reserves no room, standing over whatever lies under it. */
function cornerLengths(rw: number, growth = 1): [string, number][] {
    return [["menu-size", menuSize(rw, MENU_MAX * growth)]];
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

/** A desktop's panel's free box: the table column less a panel's gap, so the bars' notices and controls stay usable. */
function desktopPanel(
    width: number,
    column: Readonly<Record<"left" | "right", number>>,
): BoardEdges {
    return {
        bottom: PANEL_GAP,
        left: column.left + PANEL_GAP,
        right: width - column.right + PANEL_GAP,
        top: PANEL_GAP,
    };
}

/**
 * What a family's sizes are solved for: the board's settled box, its family, its chrome's tier and px (`tierChrome`'s,
 * which a phone grows on its own path) and its page's slots.
 */
interface BoardFrame {
    readonly box: BoardBox;
    readonly chrome: ChromeTier;
    readonly tier: TierChrome;
    readonly family: BoardFamily;
    readonly slots: BoardSlots;
    readonly faceFloor?: number;
    /** How much wider a phone plane's gap under the top strip is than the chrome's, so the camera shows the chrome's. */
    readonly topGap?: number;
    /** A phone plane's side strips beside the own row or above it, as the flat board's stand. */
    readonly beside?: boolean;
    /** How much higher a phone plane's centre ends, so the camera shows it clear of the flat decisions' band (px). */
    readonly coreLift?: number;
    /** Whether a phone's centre gives the top river's centre-facing edge room off its top, from its spare height. */
    readonly topEdgeRoom?: boolean;
    /** A desktop plane's arrangement as its flat board's; every arrangement where not given. */
    readonly arrangement?: DesktopArrangement;
}

/** A family's laid sizes and, off a phone, where its controls stand. */
interface LaidBoard {
    readonly lengths: BoardLengths;
    readonly arrangement: DesktopArrangement | null;
}

/**
 * A desktop's root sizes and the lengths the stylesheet reads with them, in px, at the largest river tile that fits,
 * with the arrangement they were laid in.
 */
function desktopLengths(frame: BoardFrame): LaidBoard {
    let rw = Math.max(1, Math.floor(frame.box.height / DESKTOP_STACK_TILES));
    let layout = desktopLayout(frame, rw);
    while (rw > 1 && !fitsDesktop(layout)) {
        rw -= 1;
        layout = desktopLayout(frame, rw);
    }
    const table = widthBoundTable(frame, rw);
    if (table === null) {
        return { arrangement: layout.arrangement, lengths: layout.lengths };
    }
    const relaid = desktopLayout(table, rw, fitsDrawnOwnRow);
    return {
        arrangement: relaid.arrangement,
        lengths: {
            ...relaid.lengths,
            "table-below": Math.ceil((frame.box.height - table.box.height) / 2),
            "table-h": table.box.height,
            "table-top": Math.floor((frame.box.height - table.box.height) / 2),
        },
    };
}

function fitsDesktop({ tall, wide }: DesktopLayout): boolean {
    return tall && wide;
}

function fitsDrawnOwnRow({ stacked, wide }: DesktopLayout): boolean {
    return stacked && wide;
}

function frameAtHeight(frame: BoardFrame, height: number): BoardFrame {
    return { ...frame, box: { height, width: frame.box.width } };
}

/**
 * A width-bound desktop's table, in the arrangement its full height lays at `rw`: as short as keeps its stack drawn, its
 * own row wide and, where the full height's controls all stand, the arrangement's controls too, plus the top hand's
 * air; null where the next river tile is not bound by the width alone or the table takes the whole height.
 */
function widthBoundTable(frame: BoardFrame, rw: number): BoardFrame | null {
    const next = desktopLayout(frame, rw + 1);
    if (!next.tall || next.wide) {
        return null;
    }
    const full = desktopLayout(frame, rw);
    const pinned = { ...frame, arrangement: full.arrangement };
    const fullHeldControls = full.misfits.length === 0;
    const height =
        leastHeight(pinned, (table) => {
            const layout = desktopLayout(table, rw, fitsDrawnOwnRow);
            return fitsDrawnOwnRow(layout) && (layout.misfits.length === 0 || !fullHeldControls);
        }) + Math.round(TOP_HAND_AIR * rw);
    return height < frame.box.height ? frameAtHeight(pinned, height) : null;
}

function leastHeight(frame: BoardFrame, holds: (table: BoardFrame) => boolean): number {
    let short = 0;
    let tall = Math.ceil(frame.box.height);
    while (tall - short > 1) {
        const middle = Math.floor((short + tall) / 2);
        if (holds(frameAtHeight(frame, middle))) {
            tall = middle;
        } else {
            short = middle;
        }
    }
    return tall;
}

/**
 * Why a desktop plan's controls do not stand where it puts them: a barless replay's band holds no replay row; the side
 * strips' lines cannot start below the counters; the counters' one row does not hold at their place; the side lines do
 * not fit between their start and end; or the pocket (`pocketRect`) does not hold the play switches, the furiten mark
 * and a field above them.
 */
type DesktopMisfit =
    | "replay-row"
    | "lines-under-counters"
    | "counters-row"
    | "lines-fit"
    | "pocket-stack";

/**
 * Where a desktop's controls stand: in the bars beside the table (`bars`); or with no bars, the felt edge to edge, the
 * counters at the table's top-left corner and the cog at the right lane's top, the play switches and the furiten mark
 * at the left lane's foot (`corner`) or in the free pocket over the left river (`pocket`, `pocketRect`), the side lines
 * then running to the own row as a barred board's.
 */
type DesktopArrangement = "bars" | "corner" | "pocket";

interface DesktopLayout {
    readonly lengths: BoardLengths;
    readonly stacked: boolean;
    readonly tall: boolean;
    readonly wide: boolean;
    /** Why its controls do not stand where its plan puts them; none where they all do. */
    readonly misfits: readonly DesktopMisfit[];
    readonly arrangement: DesktopArrangement;
}

/**
 * Where a desktop's counters stand: in the left bar; over the left strip's lane with the side strips' lines starting
 * below them; shrunk below their least where neither holds their one row; or, on a barless board, in the table's top-left corner
 * over the lane and the top line's far end, the side strips' lines starting below them and the cog.
 */
type CountersPlace = "bar" | "lane" | "shrunk" | "corner";

/** A desktop's bar, where its counters stand at it and its arrangement: the table's sizes solved for them. */
interface DesktopPlan {
    readonly bar: number;
    readonly counters: CountersPlace;
    readonly arrangement: DesktopArrangement;
}

/**
 * The plans a desktop tries, best first, each with the share of the river tile its own tile asks (the wanted share,
 * then the least): barred at each share, the play switches named, then lettered at the least bar, the counters' one row
 * over the lane, then in a bar widened to hold it; then barless, at the corner at both shares before the pocket at
 * both. Only `arrangement`'s plans where it is given.
 */
function desktopPlans(
    tier: TierChrome,
    rw: number,
    arrangement?: DesktopArrangement,
): readonly (DesktopPlan & { readonly share: number })[] {
    const named = Math.max(BAR_MIN, namedSwitchesBar(tier));
    const countersRoom = countersBar(rw);
    const bars = named > BAR_MIN ? [named, BAR_MIN] : [BAR_MIN];
    const shares = [OWN_BY_RIVER_WANTED, OWN_BY_RIVER_LEAST];
    const barred = shares.flatMap((share) =>
        bars.flatMap((bar) => [
            { arrangement: "bars" as const, bar, counters: "lane" as const, share },
            {
                arrangement: "bars" as const,
                bar: Math.max(bar, countersRoom),
                counters: "bar" as const,
                share,
            },
        ]),
    );
    const barless = (["corner", "pocket"] as const).flatMap((barlessArrangement) =>
        shares.map((share) => ({
            arrangement: barlessArrangement,
            bar: 0,
            counters: "corner" as const,
            share,
        })),
    );
    const plans = [...barred, ...barless];
    return arrangement === undefined
        ? plans
        : plans.filter((plan) => plan.arrangement === arrangement);
}

/**
 * A desktop's layout at `rw`: the first of its plans (`desktopPlans`) whose own tile holds its share, whose controls
 * stand (no misfit) and which `fits`; else the bars with the counters shrunk.
 */
function desktopLayout(
    frame: BoardFrame,
    rw: number,
    fits: (layout: DesktopLayout) => boolean = fitsDesktop,
): DesktopLayout {
    const tier = grownChrome(frame.tier, chromeGrowth(frame.chrome, rw));
    const plans = desktopPlans(tier, rw, frame.arrangement).filter(
        (plan) => desktopOwnTile({ bar: plan.bar, rw, width: frame.box.width }) >= plan.share * rw,
    );
    for (const plan of plans) {
        const layout = desktopAt(frame, rw, plan);
        if (layout.ownShare >= plan.share && layout.misfits.length === 0 && fits(layout)) {
            return layout;
        }
    }
    return desktopAt(frame, rw, { arrangement: "bars", bar: BAR_MIN, counters: "shrunk" });
}

/** Each plan a desktop tries at a river tile, whatever its own tile's share, with why its controls misfit there. */
function desktopPlanMisfits(
    input: BoardInput,
    rw: number,
): readonly { readonly plan: DesktopPlan; readonly misfits: readonly DesktopMisfit[] }[] {
    const frame = boardFrame(input);
    const tier = grownChrome(frame.tier, chromeGrowth(frame.chrome, rw));
    return desktopPlans(tier, rw).map((plan) => ({
        misfits: desktopAt(frame, rw, plan).misfits,
        plan,
    }));
}

/** The px the left bar takes to hold the counters' one row at their least indicator, their gaps counted. */
function countersBar(rw: number): number {
    return BAR_GAP + countersAt(leastDora(rw)).width + FIELD_STRIP_GAP;
}

/** Whether the counters' one row at their least indicator stands where `place` puts it. */
function countersHold({
    colLeft,
    place,
    rw,
}: {
    readonly colLeft: number;
    readonly place: CountersPlace;
    readonly rw: number;
}): boolean {
    const row = countersAt(leastDora(rw)).width;
    const holds: Readonly<Record<CountersPlace, boolean>> = {
        bar: row <= fieldRight(colLeft) - BAR_GAP,
        corner: true,
        lane: row <= laneEdge(colLeft, rw) - BAR_GAP,
        shrunk: false,
    };
    return holds[place];
}

/** A desktop's least dora indicator (px). */
function leastDora(rw: number): number {
    return Math.ceil(DORA_BY_RIVER_LEAST * rw);
}

/**
 * Where a desktop's counters end over the left strip's lane: `COUNTERS_AIR_BY_RIVER` of a river tile short of the
 * lane's inner edge, so the card never reads as one of the top strip's melds (px).
 */
function laneEdge(colLeft: number, rw: number): number {
    return colLeft + sideLane(rw) - COUNTERS_AIR_BY_RIVER * rw;
}

/**
 * Where the side strips' lines start: centred on the core within the table's height, or below the counters where they
 * stand over the left strip's lane (`countersFoot`), never past the table's foot (px).
 */
function sideLinesStart({
    countersFoot,
    cy,
    height,
    reach,
}: Readonly<Record<"countersFoot" | "cy" | "height" | "reach", number>>): number {
    const centred = Math.max(0, Math.min(cy - reach / 2, height - reach));
    return Math.min(Math.max(centred, countersFoot), height - reach);
}

/** A desktop's layout at a river tile and a plan, with its own tile's share of the river tile. */
function desktopAt(
    frame: BoardFrame,
    rw: number,
    plan: DesktopPlan,
): DesktopLayout & { readonly ownShare: number } {
    const { box, chrome, tier: tierAtRecord } = frame;
    const { width, height } = box;
    const growth = chromeGrowth(chrome, rw);
    const tier = grownChrome(tierAtRecord, growth);
    const { controlH } = tier;
    const rh = rw * TILE_ASPECT;
    const edge = Math.round(TILE_EDGE_SHARE * rw);
    const gap = desktopRiverGap(rw);
    const lane = sideLane(rw);
    const fitted = desktopOwnTile({ bar: plan.bar, rw, width });
    const column = desktopTable({ gap, ow: fitted, rw, width });
    const rowRoom = column.right - column.left - 2 * lane;
    const wholeOwn = Math.floor(OWN_BY_RIVER_OFF_PHONE * rw);
    const ow = Math.max(fitted, Math.min(wholeOwn, Math.floor(rowRoom / FULL_HAND)));
    const reserved = ownRow({
        height,
        margin: 0,
        ow: wholeOwn,
        ownMeldTile: desktopOwnMeldTile(rw, wholeOwn),
    });
    const { handTop, oh, ownMeldRise, ownMeldTile } = ownRow({
        height,
        margin: 0,
        ow,
        ownMeldTile: desktopOwnMeldTile(rw, ow),
    });
    const centreHeight = DESKTOP_CENTRE_TILES * rw;
    const centreWidth = RIVER_ROW_SIZE * rw;
    const drop = latestDropGap(rw);
    const decisionH = Math.max(DECISION_FLOOR, Math.floor(DECISION_BY_RIVER * rw));
    const topGap = gap + edge;
    const aboveCentre = drop + riverRows(rw, topGap);
    const core = aboveCentre + centreHeight + drop + riverRows(rw, gap);
    const coreRoomTop = rh + TOP_HAND_BACK_EDGE_SHARE * rw + TOP_HAND_GAP * rw;
    const slack = handTop - ownMeldRise - edge - coreRoomTop - core;
    const coreTop = coreRoomTop + (plan.counters === "corner" ? slack / 2 : slack);
    const cy = coreTop + aboveCentre + centreHeight / 2;
    const decisionTier = atDecisionScale(tier, decisionH);
    const reach = sideStripReach(rw);
    const place = plan.counters;
    const cog = menuSize(rw, MENU_MAX * growth);
    const { linesFloor } = desktopCounters({ cog, colLeft: column.left, place, rw });
    const laneFoot =
        plan.arrangement === "corner"
            ? laneFootTop({ handTop, height, oh, rw, tier }) - LINE_PLATE_GAP
            : height;
    const linesFoot = Math.min(laneFoot, height);
    const linesStart = sideLinesStart({ countersFoot: linesFloor, cy, height: linesFoot, reach });
    const ownPill = handTop + oh - tier.pillH;

    const lengths = Object.fromEntries([
        ...chromeLengths(decisionTier),
        ["action-text", actionText(decisionH, decisionTier.actionMinW)],
        ["badge-h", plateBoxHeight(tier)],
        ["decision-gap", DECISION_GAP_SHARE * decisionH],
        ["decision-h", decisionH],
        ...cornerLengths(rw, growth),
        ...panelLengths(desktopPanel(width, column)),
        ["col-left", column.left],
        ["col-right", column.right],
        ["control-h", controlH],
        ["core-top", coreTop],
        ["hand-top", handTop],
        ["lines-start", linesStart],
        ["m", 0],
        ["oh", oh],
        ["ow", ow],
        ["own-meld-rise", ownMeldRise],
        ["own-meld-tile", ownMeldTile],
        ["river-foot", coreTop + core + edge],
        ...coreLengths(
            { cx: width / 2, cy, height: centreHeight, rw, width: centreWidth },
            {
                drop,
                gap,
                latestGap: LATEST_DISCARD_GAP,
                rightLift: rightRiverLift(rw, gap),
                topGap,
            },
        ),
    ]);
    const linesEnd = plan.arrangement === "corner" ? laneFoot : ownPill - LINE_PLATE_GAP;
    const linesBelowCounters = place !== "corner" || linesStart >= linesFloor;
    const bandWidth = column.right - lane - ACTIONS_GAP - (width - centreWidth) / 2;
    const replayHeld =
        place !== "corner" ||
        frame.slots.band !== "replay" ||
        replayRowSide(bandWidth, tier.replayGap) >= REPLAY_CONTROL_FLOOR;
    const checks: readonly (readonly [DesktopMisfit, boolean])[] = [
        ["replay-row", replayHeld],
        ["lines-under-counters", linesBelowCounters],
        ["counters-row", countersHold({ colLeft: column.left, place, rw })],
        ["lines-fit", linesFloor === 0 || linesStart + reach <= linesEnd],
        [
            "pocket-stack",
            plan.arrangement !== "pocket" ||
                pocketHolds(
                    tier,
                    pocketRect((name) => lengths[name] ?? 0),
                ),
        ],
    ];
    return {
        arrangement: plan.arrangement,
        lengths,
        misfits: checks.filter(([, holds]) => !holds).map(([misfit]) => misfit),
        ownShare: fitted / rw,
        stacked: slack >= 0 && reach <= height,
        tall:
            reserved.handTop - reserved.ownMeldRise - edge - coreRoomTop - core >= 0 &&
            reach <= height,
        wide: fitted >= OWN_BY_RIVER_LEAST * rw && column.left >= Math.min(plan.bar, BAR_MIN),
    };
}

/**
 * The left river's longest reach under the centre's middle: its rows from the centre's top, a sideways riichi tile, the
 * latest discard's gap and a tile's edge (px).
 */
function leftRiverReach(rw: number, drop: number): number {
    return (
        -(DESKTOP_CENTRE_TILES / 2) * rw +
        ROW_BEFORE_SIDEWAYS * LYING_Y_SHARE * rw +
        rw * TILE_ASPECT * LYING_Y_SHARE +
        drop +
        TILE_EDGE_SHARE * rw
    );
}

/** The own row at an own tile: its top, its tile's height, its melds' tile and the rise two of them take over the hand. */
type OwnRow = Readonly<
    Record<"handTop" | "oh" | "ownMeldLift" | "ownMeldRise" | "ownMeldTile", number>
>;

/** A desktop's own melds' largest tile: the river tile, never past the own tile's, never under the face floor. */
function desktopOwnMeldTile(rw: number, ow: number): number {
    return Math.max(FACE_FLOOR, Math.min(OWN_MELD_SCALE * rw, ow));
}

/** The densest own melds a row holds: four open kans. */
const FOUR_OPEN_KANS: readonly MeldShape[] = Array.from({ length: 4 }, () => ({
    depth: UPRIGHT_DEPTH,
    units: 3 + SIDEWAYS_UNITS,
}));

function fourKansOwnMeldTile(
    row: Readonly<Record<"cap" | "gap" | "ow" | "width", number>>,
): number {
    return fitOwnMelds(row, FOUR_OPEN_KANS);
}

/** How far the own hand's standing body runs past its box, in whole pixels. */
function handFoot(ow: number): number {
    return Math.floor(ow * STANDING_OVERHANG);
}

/**
 * The own row at an own tile (px): its top on the board's bottom less the tile and its edge or the `margin`, whichever
 * is deeper (a desktop keeps none, a phone its margin), its melds at `ownMeldTile`.
 */
function ownRow({
    height,
    margin,
    meldsLiftedOverFoot = false,
    ow,
    ownMeldTile,
}: Readonly<Record<"height" | "margin" | "ow" | "ownMeldTile", number>> & {
    readonly meldsLiftedOverFoot?: boolean;
}): OwnRow {
    const oh = ow * TILE_ASPECT;
    const meldsEdge = ownMeldTile * TILE_EDGE_SHARE;
    const foot = Math.max(margin, handFoot(ow), meldsLiftedOverFoot ? 0 : meldsEdge);
    const ownMeldLift = Math.max(0, Math.ceil(meldsEdge - foot));
    return {
        handTop: height - foot - oh,
        oh,
        ownMeldLift,
        ownMeldRise: Math.max(0, STACKED_DEPTH * LYING_Y_SHARE * ownMeldTile + ownMeldLift - oh),
        ownMeldTile,
    };
}

/**
 * A desktop tier with its decision control’s width set from its height;
 * the play switches stay the tier's, so the bar holds them named and no chip goes under the control floor.
 */
function atDecisionScale(tier: TierChrome, decisionH: number): TierChrome {
    return {
        ...tier,
        actionMinW: DECISION_WIDTH_SHARE * decisionH,
    };
}

/**
 * A phone's chrome at its river tile: the small tier's px, growing with the river tile past `PHONE_CHROME_RIVER`; its
 * dora as large as a river tile, never under the chrome's.
 */
function phoneChrome(rw: number): PhoneChrome {
    const scale = Math.max(1, rw / PHONE_CHROME_RIVER);
    const control = PHONE_CHROME.controlH * scale;
    return {
        ...PHONE_CHROME,
        actionMinW: PHONE_CALL_W,
        controlH: control,
        doraW: Math.max(PHONE_CHROME.doraW, rw),
        movesH: control,
        pillH: PHONE_CHROME.pillH * scale,
        switchH: control,
    };
}

/** The chrome px the stylesheet draws with, by its names. */
function chromeLengths(tier: TierChrome): [string, number][] {
    return [
        ["action-min-w", tier.actionMinW],
        ["callout-cap", tier.calloutCap],
        ["chip-gap", tier.chipGap],
        ["switch-label-w", tier.switchLabelW],
        ["cue-w", tier.cueW],
        ["moves-h", tier.movesH],
        ["pill-h", tier.pillH],
        ["switch-h", tier.switchH],
        ["switch-text", tier.switchText],
        ["text", tier.text],
    ];
}

/**
 * A phone's table column, centred: `TABLE_COLUMN_TILES` river tiles wide, wider where the core and both side lanes need
 * more (a centre at its least width over a small river tile), as far as the bars keep `barLeast` wide enough that
 * the top strip's line holds four kans at the face floor beside its centred hand, and with both side lanes `beside` the
 * own row where they run down past it. Its edges (px).
 */
function phoneColumn(
    {
        barLeast,
        beside,
        width,
    }: { readonly barLeast: number; readonly beside: boolean; readonly width: number },
    { centreWidth, ow, rw }: Readonly<Record<"centreWidth" | "ow" | "rw", number>>,
): Readonly<Record<"left" | "right", number>> {
    const lane = sideLane(rw);
    const core = centreWidth + 2 * sideRiverReach(rw, riverGap(rw));
    const topKans =
        2 * (kansLineReach(rw, { share: LYING_X_SHARE }) - fullReach(rw, "top") / 2 + lane);
    const columnWidth = Math.max(
        TABLE_COLUMN_TILES * rw,
        core + 2 * (lane + PLATE_GAP),
        Math.min(width - 2 * barLeast, topKans),
        beside ? FULL_HAND * ow + 2 * (lane + STEP_IN_GAP) : 0,
    );
    const left = (width - columnWidth) / 2;
    return { left, right: left + columnWidth };
}

/** A phone's panel's free box: equal gaps, a replay's right one moved clear of its controls by its shell. */
function phonePanel(): BoardEdges {
    return { bottom: PANEL_GAP, left: PANEL_GAP, right: PANEL_GAP, top: PANEL_GAP };
}

/** A phone's felt keeps the page gutter's air past the own row and the side lanes. */
const FELT_AIR = PAGE_GUTTER;

/** A phone's rails keep their controls this far off the felt (px). */
const RAIL_GAP = 4;

/** A full hand at the own tile's floor and the felt's air beside it: the narrowest felt a phone wants (px). */
const LEAST_FELT = FULL_HAND * PHONE_OWN_FLOOR + 2 * FELT_AIR;

/**
 * A phone's rail beside its felt, either side alike: as wide as the widest of the cog, a replay's controls standing in
 * it and a column of play switches needs, the margin and the rail's gap (px).
 */
function phoneRail(
    chrome: PhoneChrome,
    { replayWidth, rw }: Readonly<Record<"replayWidth" | "rw", number>>,
): number {
    return chrome.m + Math.max(menuSize(rw), replayWidth, chrome.switchH) + RAIL_GAP;
}

/**
 * The width a phone's felt wants with its lanes above the own row (px): `PHONE_FELT_BY_HEIGHT` of the board's height, or
 * `LEAST_FELT` where that is wider, within its rails (`rail` each); a board too narrow for `LEAST_FELT` within them
 * narrows its rails first, down to none. The own tile is never larger than a full hand and its air in it holds.
 */
function phoneFeltWanted({
    height,
    rail,
    width,
}: Readonly<Record<"height" | "rail" | "width", number>>): number {
    return Math.min(
        Math.max(PHONE_FELT_BY_HEIGHT * height, LEAST_FELT),
        phoneFeltWithin({ rail, width }),
    );
}

/** The widest a phone's felt with its lanes above the own row stands within its rails (`phoneFeltWanted`), px. */
function phoneFeltWithin({ rail, width }: Readonly<Record<"rail" | "width", number>>): number {
    return Math.max(width - 2 * rail, Math.min(width, LEAST_FELT));
}

/**
 * A phone's felt, the table's one rectangle (its edges, px): with the lanes above the own row, centred, as wide as it
 * wants (`phoneFeltWanted`), never narrower than the table column and its air; with the lanes beside the own row (a
 * browser's short box), as wide as its rails (`rail` each) leave it, holding the column and its air, that air giving way
 * to the rails, down to their controls without the rails' gap, before the column narrows.
 */
function phoneFelt({
    beside,
    column,
    height,
    rail,
    width,
}: {
    readonly beside: boolean;
    readonly column: Readonly<Record<"left" | "right", number>>;
    readonly height: number;
    readonly rail: number;
    readonly width: number;
}): Readonly<Record<"left" | "right", number>> {
    if (beside) {
        const left = Math.min(rail, Math.max(column.left - FELT_AIR, rail - RAIL_GAP));
        return { left, right: width - left };
    }
    const wanted = phoneFeltWanted({ height, rail, width });
    const across = Math.min(width, Math.max(column.right - column.left + 2 * FELT_AIR, wanted));
    const left = (width - across) / 2;
    return { left, right: left + across };
}

/**
 * Where a phone replay's controls stand, and their block (`phoneReplayBlock`): in the right rail, down its whole height
 * beside the own row, where the lanes stand beside the own row or the rail holds them in one column; else their two
 * columns at the right bar's foot above the own row, at the felt's edge, so the rails keep one control's width.
 */
function phoneReplayPlace({
    beside,
    chrome,
    feltRight,
    height,
    lineEnd,
    rw,
    width,
}: {
    readonly beside: boolean;
    readonly chrome: Pick<PhoneChrome, "m" | "movesH" | "replayGap">;
} & Readonly<Record<"feltRight" | "height" | "lineEnd" | "rw" | "width", number>>): {
    readonly block: ReturnType<typeof phoneReplayBlock>;
    readonly inRail: boolean;
    readonly room: Readonly<Record<"bottom" | "top", number>>;
} {
    const { m } = chrome;
    const rail = phoneRailRoom({ height, m, rw });
    const railBlock = phoneReplayBlock(chrome, rail.bottom - rail.top);
    const inRail =
        beside ||
        (railBlock.columns === 1 && width - feltRight >= m + railBlock.width + RAIL_GAP - 0.001);
    if (inRail) {
        return { block: railBlock, inRail, room: rail };
    }
    const bar = { bottom: phoneControlsBottom(lineEnd), top: phoneUnderCog(m, rw) };
    return { block: phoneReplayBlock(chrome, bar.bottom - bar.top), inRail, room: bar };
}

/**
 * A phone's lengths at a river and own tile, in px; whether its places fit them: the centre at its least height, both
 * side strips' lines a full concealed hand long (three pons may reach into the top margin) from the top margin to the
 * bars' foot (above the own row, or `beside` it at the board's foot), both bars as wide as the wider one's contents need,
 * the felt (`phoneFelt`) within its rails holding the own row and its air, the own tile no larger than the felt's wanted
 * width holds a full hand in, and whether the decisions' band holds `call_prompt`'s rows and a replay's controls their place.
 */
function phoneLayout(
    frame: BoardFrame,
    { beside, ow, rw }: { readonly beside: boolean; readonly ow: number; readonly rw: number },
): {
    readonly band: BoardRect;
    readonly fits: boolean;
    readonly holdsKans: boolean;
    readonly holdsPrompt: boolean;
    readonly holdsReplay: boolean;
    readonly lanesFit: boolean;
    readonly lengths: BoardLengths;
    readonly ownCap: number;
} {
    const { box } = frame;
    const { height, width } = box;
    const chrome = phoneChrome(rw);
    const { controlH, coreGap, m, sep } = chrome;
    const rh = rw * TILE_ASPECT;
    const gap = riverGap(rw);
    const railRoom = phoneRailRoom({ height, m, rw });
    const replayWidth = phoneReplayBlock(chrome, railRoom.bottom - railRoom.top).width;
    const rail = phoneRail(chrome, { replayWidth: beside ? replayWidth : 0, rw });
    const barLeast = Math.max(
        phoneLeftBarLeast(chrome),
        phoneRightBarLeast(chrome, replayWidth, rw),
    );
    const centreWidth = Math.max(RIVER_ROW_SIZE * rw, PHONE_CENTRE_MIN_WIDTH);
    const column = phoneColumn({ barLeast, beside, width }, { centreWidth, ow, rw });
    const felt = phoneFelt({ beside, column, height, rail, width });
    const ownStart = (width - FULL_HAND * ow) / 2;
    const ownEnd = beside ? width - ownStart : felt.right - FELT_AIR;
    const { handTop, oh, ownMeldLift, ownMeldRise, ownMeldTile } = ownRow({
        height,
        margin: m,
        meldsLiftedOverFoot: true,
        ow,
        ownMeldTile: fourKansOwnMeldTile({
            cap: ow,
            gap,
            ow,
            width: ownEnd - ownStart,
        }),
    });
    const rowTop = phoneRowTop({ handTop, ownMeldRise, rw });
    const foot = beside ? height - m : rowTop;
    const line = foot - m;
    const coreTop = m + rh + sep + (frame.topGap ?? 0);
    const rows = riverRows(rw, gap);
    const latestDrop = phoneLatestDrop(rw);
    const topEdge = Math.ceil(TILE_EDGE_SHARE * rw);
    const topEdgeHeld = Math.max(0, Math.min(topEdge, topEdge + PHONE_TOP_EDGE_CLEAR - gap));
    const spareRoom =
        handTop - coreGap - (frame.coreLift ?? 0) - 2 * (latestDrop + rows) - topEdgeHeld - coreTop;
    const edgeRoomPastHeld = frame.topEdgeRoom
        ? Math.max(
              0,
              Math.min(
                  topEdge - topEdgeHeld,
                  spareRoom - PHONE_CENTRE_MIN_HEIGHT + CENTRE_EDGE_GIVE,
              ),
          )
        : 0;
    const edgeRoom = topEdgeHeld + edgeRoomPastHeld;
    const topGap = gap + edgeRoom;
    const centreTop = coreTop + latestDrop + rows + edgeRoom;
    const centreRoom = spareRoom - edgeRoomPastHeld;
    function lengthsAt(laid: BoardLengths): (name: string) => number {
        return (name) => laid[name] ?? 0;
    }
    const decisionH = phoneDecisionHeight(height);
    const roomy = layLengths(centreRoom);
    const roomyBand = phoneActions(lengthsAt(roomy));
    const bandShort =
        phonePromptHeight(roomyBand.right - roomyBand.left, decisionH) -
        (roomyBand.bottom - roomyBand.top);
    const centreGivesBand = Math.max(0, Math.min(bandShort, centreRoom - PHONE_CENTRE_MIN_HEIGHT));
    const lengths = centreGivesBand > 0 ? layLengths(centreRoom - centreGivesBand) : roomy;
    function layLengths(heightRoom: number): BoardLengths {
        const cy = centreTop + heightRoom / 2;
        return Object.fromEntries([
            ...chromeLengths(chrome),
            ["action-text", actionText(decisionH, chrome.actionMinW)],
            ["decision-h", decisionH],
            ["decision-gap", PHONE_DECISION_GAP],
            ["badge-h", plateBoxHeight(chrome)],
            ...cornerLengths(rw),
            ...panelLengths(phonePanel()),
            ["col-left", column.left],
            ["col-right", column.right],
            ["control-h", controlH],
            ["core-top", coreTop],
            ["felt-left", felt.left],
            ["felt-right", felt.right],
            ["hand-top", handTop],
            ["lines-end", foot],
            ["m", m],
            ["oh", oh],
            ["ow", ow],
            ["own-end", ownEnd],
            ["own-meld-lift", ownMeldLift],
            ["own-meld-rise", ownMeldRise],
            ["own-meld-tile", ownMeldTile],
            ["own-start", ownStart],
            ...coreLengths(
                { cx: width / 2, cy, height: heightRoom, rw, width: centreWidth },
                {
                    drop: latestDrop,
                    gap,
                    latestGap: phoneLatestGap(rw),
                    rightLift: rightRiverLift(rw, gap),
                    topGap,
                },
            ),
            ["side-reach", phoneSideReach(rw, line, frame.faceFloor)],
        ]);
    }
    const at = lengthsAt(lengths);
    const band = phoneActions(at);
    const lanesFit =
        spareRoom >= PHONE_CENTRE_MIN_HEIGHT &&
        fullReach(rw, "left") <= rowTop - m &&
        ponsReach(rw, frame.faceFloor) <= foot &&
        column.left >= barLeast - 0.001;
    const ownCap = beside
        ? Infinity
        : Math.floor((phoneFeltWanted({ height, rail, width }) - 2 * FELT_AIR) / FULL_HAND);
    const handInFelt =
        beside ||
        (ow <= ownCap && felt.right - felt.left <= phoneFeltWithin({ rail, width }) + 0.001);
    const replay = phoneReplayPlace({
        beside,
        chrome,
        feltRight: felt.right,
        height,
        lineEnd: foot,
        rw,
        width,
    });
    return {
        band,
        fits: lanesFit && handInFelt,
        holdsKans: tightKansReach(rw, frame.faceFloor) <= line + STRIP_CONTROL_CLEAR,
        holdsPrompt:
            band.bottom - band.top >= phonePromptHeight(band.right - band.left, decisionH) - 0.001,
        holdsReplay: replay.block.height <= replay.room.bottom - replay.room.top,
        lanesFit,
        lengths,
        ownCap,
    };
}

/**
 * A phone's layout at a river and own tile: its side lanes at the table column's edges above the own row, or beside the
 * own row, the lanes and bars running down past it, where above it they do not fit, or do not hold `PHONE_LINE_KANS`
 * or the decisions' band `call_prompt` or a replay's controls, and beside it they fit. Lanes that stand above it are
 * never moved beside it for an own tile larger than the felt holds: that own tile does not fit.
 */
function phoneLaid(
    frame: BoardFrame,
    tiles: Readonly<Record<"ow" | "rw", number>>,
): ReturnType<typeof phoneLayout> {
    if (frame.beside !== undefined) {
        return phoneLayout(frame, { ...tiles, beside: frame.beside });
    }
    const above = phoneLayout(frame, { ...tiles, beside: false });
    if (holdsAbove(above)) {
        return above;
    }
    const beside = phoneLayout(frame, { ...tiles, beside: true });
    return beside.fits || !above.fits ? beside : above;
}

/** Whether a phone's lanes stand above its own row at a layout's tiles, all they hold held, the felt aside. */
function holdsAbove(laid: ReturnType<typeof phoneLayout>): boolean {
    return laid.lanesFit && laid.holdsKans && laid.holdsPrompt && laid.holdsReplay;
}

/** How far the decisions' band may move for the top river's edge room and still count as kept (px). */
const BAND_KEPT_TOLERANCE = 0.5;

/**
 * A phone laid at `tiles` with its top river's edge given room off the centre's top, where the centre's spare height
 * allows, everything the plain layout holds still holds and its decisions' band keeps its place and width; else the
 * plain layout. The tiles never change for it.
 */
function phoneLaidWithEdgeRoom(
    frame: BoardFrame,
    tiles: Readonly<Record<"ow" | "rw", number>>,
): ReturnType<typeof phoneLayout> {
    const plain = phoneLaid(frame, tiles);
    const roomy = phoneLaid({ ...frame, topEdgeRoom: true }, tiles);
    const keeps = (["fits", "holdsKans", "holdsPrompt", "holdsReplay"] as const).every(
        (check) => !plain[check] || roomy[check],
    );
    const bandKept =
        roomy.band.left <= plain.band.left + BAND_KEPT_TOLERANCE &&
        roomy.band.right >= plain.band.right - BAND_KEPT_TOLERANCE &&
        roomy.band.top <= plain.band.top + BAND_KEPT_TOLERANCE;
    return keeps && bandKept ? roomy : plain;
}

/** `lengths` laid again at their own tiles with the top river's edge room (`phoneLaidWithEdgeRoom`). */
function withEdgeRoom(frame: BoardFrame, lengths: BoardLengths): BoardLengths {
    return phoneLaidWithEdgeRoom(frame, { ow: lengths["ow"] ?? 0, rw: lengths["rw"] ?? 0 }).lengths;
}

/**
 * A phone's lengths at the largest river tile that fits above `ownFloor`, then the largest own tile that fits with it,
 * at most as wide as lets a full hand stand within the board's width less its margins and at least 4/3 of the river
 * tile, never under the floor, which wins where both cannot hold, and `holdingPrompt` its band `call_prompt`'s rows;
 * null where no pair fits. The own tile is the largest whose right bar holds a replay's column, else the least.
 */
function phoneSolve(
    frame: BoardFrame,
    { holdingPrompt, ownFloor }: { readonly holdingPrompt: boolean; readonly ownFloor: number },
): BoardLengths | null {
    const { box } = frame;
    const widest = Math.max(ownFloor, Math.floor((box.width - 2 * PHONE_CHROME.m) / FULL_HAND));
    for (
        let rw = Math.floor(box.height / PHONE_MAX_RIVER_SHARE);
        rw >= PHONE_SMALLEST_RIVER;
        rw -= 1
    ) {
        const least = Math.max(ownFloor, Math.ceil(TILE_ASPECT * rw));
        for (let ow = widest; ow >= least; ow -= 1) {
            const laid = phoneLaid(frame, { ow, rw });
            if (
                laid.fits &&
                (laid.holdsPrompt || !holdingPrompt) &&
                (laid.holdsReplay || ow === least)
            ) {
                return laid.lengths;
            }
        }
    }
    return null;
}

function phoneSolveHoldingPrompt(frame: BoardFrame, ownFloor: number): BoardLengths | null {
    return (
        phoneSolve(frame, { holdingPrompt: true, ownFloor }) ??
        phoneSolve(frame, { holdingPrompt: false, ownFloor })
    );
}

function phoneLengthsRiverFirst(frame: BoardFrame): BoardLengths {
    const solved = phoneSolveHoldingPrompt(frame, PHONE_OWN_FLOOR);
    if (solved !== null && (solved["rw"] ?? 0) >= FACE_FLOOR) {
        return withEdgeRoom(frame, solved);
    }
    const tapFloored = phoneSolveHoldingPrompt(frame, PHONE_OWN_TAP_FLOOR);
    if (tapFloored !== null && (tapFloored["rw"] ?? 0) > (solved?.["rw"] ?? 0)) {
        return withEdgeRoom(frame, tapFloored);
    }
    return solved === null
        ? phoneLayout(frame, { beside: false, ow: PHONE_OWN_TAP_FLOOR, rw: PHONE_SMALLEST_RIVER })
              .lengths
        : withEdgeRoom(frame, solved);
}

function phoneOwnAtRiver(
    frame: BoardFrame,
    {
        holdingPrompt,
        ownCeiling,
        ownFloor,
        rw,
        smallestWanted,
    }: {
        readonly holdingPrompt: boolean;
        readonly ownCeiling: number;
        readonly ownFloor: number;
        readonly rw: number;
        readonly smallestWanted: number;
    },
): BoardLengths | null {
    const widest = Math.min(
        ownCeiling,
        Math.max(ownFloor, Math.floor((frame.box.width - 2 * PHONE_CHROME.m) / FULL_HAND)),
    );
    const least = Math.max(ownFloor, Math.ceil(TILE_ASPECT * rw));
    for (let ow = widest; ow >= Math.max(least, smallestWanted); ow -= 1) {
        const laid = phoneLaid(frame, { ow, rw });
        if (
            laid.fits &&
            (laid.holdsPrompt || !holdingPrompt) &&
            (laid.holdsReplay || ow === least)
        ) {
            return laid.lengths;
        }
    }
    return null;
}

function phoneOwnFitCeiling(
    frame: BoardFrame,
    { ownCeiling, ownFloor }: { readonly ownCeiling: number; readonly ownFloor: number },
): number | null {
    const widest = Math.min(
        ownCeiling,
        Math.max(ownFloor, Math.floor((frame.box.width - 2 * PHONE_CHROME.m) / FULL_HAND)),
    );
    for (let ow = widest; ow >= ownFloor; ow -= 1) {
        if (phoneLaid(frame, { ow, rw: FACE_FLOOR }).fits) {
            return ow;
        }
    }
    return null;
}

function phoneSolveOwnLed(
    frame: BoardFrame,
    pass: {
        readonly holdingPrompt: boolean;
        readonly ownCeiling: number;
        readonly ownFloor: number;
    },
): BoardLengths | null {
    const fitsAtFaceFloor = phoneOwnFitCeiling(frame, pass);
    if (fitsAtFaceFloor === null) {
        return null;
    }
    const bounded = { ...pass, ownCeiling: fitsAtFaceFloor };
    const tallestRiver = Math.floor(frame.box.height / PHONE_MAX_RIVER_SHARE);
    let largestOwn = 0;
    for (let rw = FACE_FLOOR; rw <= tallestRiver; rw += 1) {
        const laid = phoneOwnAtRiver(frame, { ...bounded, rw, smallestWanted: largestOwn + 1 });
        largestOwn = laid?.["ow"] ?? largestOwn;
    }
    if (largestOwn === 0) {
        return null;
    }
    for (let rw = tallestRiver; rw >= FACE_FLOOR; rw -= 1) {
        const laid = phoneOwnAtRiver(frame, {
            ...bounded,
            rw,
            smallestWanted: largestOwn - PHONE_OWN_GIVEN_FOR_RIVER,
        });
        if (laid !== null) {
            return laid;
        }
    }
    return null;
}

const PHONE_OWN_LED_RANGES = [
    { ownCeiling: Infinity, ownFloor: PHONE_OWN_FLOOR },
    { ownCeiling: PHONE_OWN_FLOOR - 1, ownFloor: PHONE_OWN_TAP_FLOOR },
] as const;

/**
 * Whether a phone's lanes stand above its own row at some river tile with the own tile its felt holds, all they hold
 * held: such a box never moves its lanes beside the own row for a larger own tile than its felt holds.
 */
function lanesHoldAbove(frame: BoardFrame): boolean {
    for (let rw = FACE_FLOOR; rw <= Math.floor(frame.box.height / PHONE_MAX_RIVER_SHARE); rw += 1) {
        const { ownCap } = phoneLayout(frame, { beside: false, ow: PHONE_OWN_FLOOR, rw });
        if (
            ownCap >= PHONE_OWN_FLOOR &&
            holdsAbove(phoneLayout(frame, { beside: false, ow: ownCap, rw }))
        ) {
            return true;
        }
    }
    return false;
}

function phoneLengths(unsettled: BoardFrame): BoardLengths {
    const frame =
        unsettled.beside === undefined && lanesHoldAbove(unsettled)
            ? { ...unsettled, beside: false }
            : unsettled;
    const anyBands = PHONE_OWN_LED_RANGES.map((range) =>
        phoneSolveOwnLed(frame, { ...range, holdingPrompt: false }),
    );
    for (const [index, range] of PHONE_OWN_LED_RANGES.entries()) {
        const promptBand =
            anyBands[index] === null
                ? null
                : phoneSolveOwnLed(frame, { ...range, holdingPrompt: true });
        if (promptBand !== null) {
            return withEdgeRoom(frame, promptBand);
        }
    }
    const anyBand = anyBands.find((laid) => laid !== null);
    return anyBand === undefined || anyBand === null
        ? phoneLengthsRiverFirst(frame)
        : withEdgeRoom(frame, anyBand);
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
    | "furiten"
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
    readonly sideNameRail: BoardRect | null;
    readonly areas: Readonly<Record<ShellSlot, BoardRect> & Partial<Record<"toasts", BoardRect>>>;
    readonly lengths: readonly [string, number][];
    readonly strips: StripRooms;
    readonly switches: SwitchesForm;
    readonly replay: ReplayForm;
}

/**
 * What the slots are placed from: the board's frame, its family's lengths by name and its chrome.
 */
interface ShellRoom {
    readonly frame: BoardFrame;
    readonly at: (name: string) => number;
    readonly tier: TierChrome;
}

/**
 * The decisions stand this far off the right strip's lane, the centre and the own melds' rise, a phone's under the
 * right badge (px).
 */
const ACTIONS_GAP = 6;

/**
 * A desktop's decision control's height in river tiles, never under `DECISION_FLOOR` (px); its gap to its height; a
 * control's least width to its height.
 */
const DECISION_BY_RIVER = 0.95;
const DECISION_FLOOR = 52;
const DECISION_GAP_SHARE = 1 / 5;
const DECISION_WIDTH_SHARE = 2;

/** A desktop's notices' toasts stand this far under the left river's longest reach (px). */
const TOASTS_RIVER_GAP = 4;

function actionText(height: number, width: number): number {
    return Math.min(height / 2, width / 4);
}

const PHONE_DECISION_GAP = 8;
const PHONE_CALL_W = 78;
const MAX_CALL_KINDS = 4;

function phoneDecisionHeight(height: number): number {
    return Math.min(48, Math.max(42, Math.floor(height / 9)));
}

/** A phone's left bar's fields keep this far off what they stand past (px). */
const FIELD_GAP = 6;

/** A phone's play switches stand in rows of this many chips, a block short enough to leave the notices their field. */
const PHONE_SWITCH_COLUMNS = 2;

/** Where the river's rows meet the board, from the tile slice's shape. */
const ROW_BEFORE_SIDEWAYS = RIVER_ROW_SIZE - 1;

/** The height all four call kinds, Pass and the timer take in a phone's band this wide, wrapping up in rows (px). */
function phonePromptHeight(bandWidth: number, rowHeight: number): number {
    const slotWidth = PHONE_CALL_W * CALL_BUTTON_SCALE * COMPACT_CALL_SCALE.size;
    const perRow = Math.max(
        1,
        Math.floor((bandWidth + PHONE_DECISION_GAP) / (slotWidth + PHONE_DECISION_GAP)),
    );
    const rows = Math.ceil((MAX_CALL_KINDS + 2) / perRow);
    return rows * rowHeight + (rows - 1) * PHONE_DECISION_GAP;
}

function phoneLeftBarLeast(chrome: PhoneChrome): number {
    const counters = countersAt(FACE_FLOOR).width;
    const switches = PHONE_SWITCH_COLUMNS * chrome.switchH;
    const notices = NOTICE_FIELD_EMS * NOTICE_TEXT_MIN;
    return chrome.m + Math.max(counters, switches, notices) + FIELD_GAP;
}

function phoneRightBarLeast(chrome: PhoneChrome, replayWidth: number, rw: number): number {
    return ACTIONS_GAP + Math.max(menuSize(rw), replayWidth) + chrome.m;
}

/** A phone's right bar's controls' top: under the cog and a gap (px). */
function phoneUnderCog(m: number, rw: number): number {
    return m + menuSize(rw) + ACTIONS_GAP;
}

/** A phone's right bar's controls' bottom: a gap above the bars' foot, where the side strips' lines end (px). */
function phoneControlsBottom(foot: number): number {
    return foot + STRIP_CONTROL_CLEAR - ACTIONS_GAP;
}

/** A phone's right rail's room for a replay's controls: under the cog and the rail's gap, down to its margin (px). */
function phoneRailRoom({
    height,
    m,
    rw,
}: Readonly<Record<"height" | "m" | "rw", number>>): Readonly<Record<"bottom" | "top", number>> {
    return { bottom: height - m, top: m + menuSize(rw) + RAIL_GAP };
}

/**
 * A desktop's decisions' place, a band along the own row's top: from the bottom river's start (the centre's left edge,
 * right of the notices' toasts) to short of the right strip's lane, under the centre and the right river's first tile
 * and over the own row's melds' rise. Its controls wrap up from its bottom right and stand over the own river and the
 * plates there, which no decision's source lies in.
 */
function desktopActions({ at }: ShellRoom): { readonly rect: BoardRect } {
    const rw = at("rw");
    return {
        rect: {
            bottom: at("hand-top") - at("own-meld-rise") - ACTIONS_GAP,
            left: at("cx") - at("hx"),
            right: at("col-right") - sideLane(rw) - ACTIONS_GAP,
            top: at("cy") + at("h") + TILE_EDGE_SHARE * rw + ACTIONS_GAP,
        },
    };
}

const PHONE_BAND_OVER_OWN_ROW = 4;
const PHONE_BAND_UNDER_CENTRE = 4;

function phoneLeftRiverEnd(at: (name: string) => number): number {
    return (
        at("cy") -
        at("h") +
        ROW_BEFORE_SIDEWAYS * LYING_Y_SHARE * at("rw") +
        at("rh") * LYING_Y_SHARE +
        at("latest-drop-gap")
    );
}

function phoneActions(at: (name: string) => number): BoardRect {
    const rw = at("rw");
    const lane = sideLane(rw);
    const bottom = at("hand-top") - at("own-meld-rise") - PHONE_BAND_OVER_OWN_ROW;
    const leftRiverEnd = phoneLeftRiverEnd(at);
    return {
        bottom,
        left:
            bottom - at("decision-h") >= leftRiverEnd
                ? at("col-left") + lane + ACTIONS_GAP
                : at("cx") - at("hx"),
        right: at("col-right") - lane - ACTIONS_GAP,
        top: at("cy") + at("h") + PHONE_BAND_UNDER_CENTRE,
    };
}

/** Clearance at a strip's outer-line limit (px). */
const STRIP_ROOM_GAP = 8;

/** Clearance around the switches' and own row's reserved footprints (px). */
const STRIP_CONTROL_CLEAR = 4;

/** How much shorter than its least a phone's centre may stand to give the top river's edge its room (px). */
const CENTRE_EDGE_GIVE = 1;

const PHONE_TOP_EDGE_CLEAR = 3;

/**
 * Where an opponent's side strips stand, by their family's places (px): the left line from `leftStart` down to
 * `leftEnd`, its melds kept off the own row from `lineClear` past that end down to the board's foot; the right one from
 * its origin `rightEnd` up to `rightStart`.
 */
interface StripPlaces {
    readonly leftStart: number;
    readonly leftEnd: number;
    readonly rightStart: number;
    readonly rightEnd: number;
    readonly lineClear: number;
    readonly ownStart: number;
    readonly topEnd: number;
    readonly topStart?: number;
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
    const colLeft = at("col-left");
    const colRight = at("col-right");
    const lane = sideLane(rw);
    const { leftEnd, leftStart, rightEnd, rightStart } = places;
    const leftLine = leftEnd - leftStart;
    const rightLine = rightEnd - rightStart;
    const top = topLine(at, places.topEnd, places.topStart);
    const pastLine = {
        depth: places.ownStart - colLeft - STEP_IN_GAP,
        from: leftEnd + places.lineClear - leftStart,
        to: frame.box.height - leftStart,
    };
    return {
        areas: {
            "strip-left": {
                bottom: leftEnd,
                left: colLeft,
                right: colLeft + lane,
                top: leftStart,
            },
            "strip-right": {
                bottom: rightEnd,
                left: colRight - lane,
                right: colRight,
                top: rightStart,
            },
            "strip-top": {
                bottom: m + STACKED_DEPTH * LYING_Y_SHARE * rw,
                left: top.start,
                right: top.anchor,
                top: m,
            },
        },
        strips: {
            floor: frame.faceFloor,
            gap: at("g") + MELD_GAP_EXTRA,
            left: { deepLine: leftLine, line: leftLine, obstacles: [pastLine] },
            right: { deepLine: rightLine, line: rightLine, obstacles: [] },
            rw,
            top: {
                ...top,
                depth: at("core-top") - TOP_CORE_CLEAR - (frame.topGap ?? 0) - m,
            },
        },
    };
}

/**
 * The top hand's line: its full reach centred, from past the left strip's lane, its start (the anchor) never past
 * `end` (px).
 */
function topLine(
    at: (name: string) => number,
    end: number,
    from = 0,
): Readonly<Record<"anchor" | "start", number>> {
    const reach = fullReach(at("rw"), "top");
    const start = Math.max(from, at("col-left") + sideLane(at("rw")));
    const anchor = Math.min(at("cx") + reach / 2, end);
    return { anchor: Math.max(start + reach, anchor), start };
}

function topHandEnd(at: (name: string) => number): number {
    return at("col-right") - sideLane(at("rw"));
}

/**
 * A desktop's side strips' lines, each as long as its reserved reach from where the layout starts them (`lines-start`):
 * centred on the core as far as the table's height allows, or under the counters and the round info where they stand
 * over the left strip's lane; the own row stands between their lanes, so nothing below the core stops them (px).
 */
function desktopSideLines({ at }: ShellRoom): Readonly<Record<"end" | "start", number>> {
    const start = at("lines-start");
    return { end: start + sideStripReach(at("rw")), start };
}

/**
 * A bar's contents keep this far off its edges and each other; the counters and the field under them this far off the
 * left strip, never narrower than the counters' least row there (px).
 */
const BAR_GAP = 6;
const FIELD_STRIP_GAP = 12;
const FIELD_LEAST = 84;

/** Where a desktop's counters and the field under them end, off the left strip at the table's edge `colLeft` (px). */
function fieldRight(colLeft: number): number {
    return Math.max(colLeft - FIELD_STRIP_GAP, Math.min(colLeft - BAR_GAP, BAR_GAP + FIELD_LEAST));
}

/** The gap between a desktop replay's moves and its options, in the gaps between its controls. */
const REPLAY_GROUP_GAPS = 2;

/**
 * A desktop replay's control: this share of a river tile, never under the control floor (px); the columns its block may
 * stand in within a small window's bar, fewest first.
 */
const REPLAY_BY_RIVER = 0.95;
const REPLAY_CONTROL_FLOOR = 40;
const REPLAY_COLUMNS = [1, 2] as const;

/** The furiten mark's height in its text's ems, and its text's least size (px); `.board-furiten` mirrors both. */
const FURITEN_EMS = 1.5;
const FURITEN_TEXT_MIN = 12;

/** The play switches' form: each switch showing its name, the letters' joined column, or a phone's two-by-two block. */
type SwitchesForm = "names" | "letters" | "block";

/**
 * A replay's controls' form: one row over the own row, or in the right bar one column or two, the moves there paired
 * back and forward with autoplay under them.
 */
type ReplayForm = "row" | "column" | "pairs";

/** The form of a replay's controls standing in a bar in so many columns. */
function barReplayForm(columns: number): ReplayForm {
    return columns === 1 ? "column" : "pairs";
}

/** What a family places in its controls' slots: their areas, the lengths their contents read, the switches' form. */
interface ControlSlots {
    readonly sideNameRail: BoardRect | null;
    readonly areas: Readonly<
        Record<"actions" | "corner" | "field" | "furiten" | "switches", BoardRect>
    >;
    readonly lengths: readonly [string, number][];
    readonly switches: SwitchesForm;
    readonly replay: ReplayForm;
}

/** A desktop replay's controls: their block's place, their side and the block's width (px). */
interface ReplayBlock {
    readonly rect: BoardRect;
    readonly side: number;
    readonly width: number;
}

/** A desktop replay's control at its wanted side: a share of a river tile, never under the control floor (px). */
function wantedReplaySide(at: (name: string) => number): number {
    return Math.max(REPLAY_CONTROL_FLOOR, Math.round(REPLAY_BY_RIVER * at("rw")));
}

/**
 * A desktop replay's controls in the decisions' band, over the own hand: the moves and then the
 * options in one row along the band's foot from its start (the bottom river's), each at its wanted side where the band
 * holds them so large; null where the band holds no row at the control floor. The row stands over the bottom river's last row, which a replay's reader steps past.
 */
function replayRow({ at, tier }: ShellRoom, band: BoardRect): ReplayBlock | null {
    const count = REPLAY_MOVES + REPLAY_OPTIONS;
    const gaps = replayRowGaps(tier.replayGap);
    const side = Math.floor(
        Math.min(
            wantedReplaySide(at),
            replayRowSide(band.right - band.left, tier.replayGap),
            band.bottom - band.top,
        ),
    );
    const width = count * side + gaps;
    const rect = {
        bottom: band.bottom,
        left: band.left,
        right: band.left + width,
        top: band.bottom - side,
    };
    return side >= REPLAY_CONTROL_FLOOR ? { rect, side, width } : null;
}

function replayRowGaps(gap: number): number {
    return (REPLAY_MOVES + REPLAY_OPTIONS - 2 + REPLAY_GROUP_GAPS) * gap;
}

/** The side a desktop replay's controls take in one row `across` px wide (px). */
function replayRowSide(across: number, gap: number): number {
    return (across - replayRowGaps(gap)) / (REPLAY_MOVES + REPLAY_OPTIONS);
}

/** A desktop replay's controls arranged in so many columns within a bar: their side, and the block they make (px). */
function replayColumnArrangement(
    { at, tier }: ShellRoom,
    room: Readonly<Record<"across" | "down", number>>,
    columns: number,
): Readonly<Record<"columns" | "height" | "side" | "width", number>> {
    const gap = tier.replayGap;
    const rows = Math.ceil(REPLAY_MOVES / columns) + Math.ceil(REPLAY_OPTIONS / columns);
    const gaps = (rows - 2 + REPLAY_GROUP_GAPS) * gap;
    const side = Math.floor(
        Math.min(
            wantedReplaySide(at),
            (room.across - (columns - 1) * gap) / columns,
            (room.down - gaps) / rows,
        ),
    );
    return {
        columns,
        height: rows * side + gaps,
        side,
        width: columns * side + (columns - 1) * gap,
    };
}

/**
 * A small window's replay controls, whose band holds no row at the control floor, in the right bar: the moves over the
 * options, in one column, or two (the moves paired) where that holds them larger or only two keep the block in the
 * bar's lower half; centred across the bar and standing on its foot, by the own row.
 */
function replayColumn(
    room: ShellRoom,
    bar: BoardRect,
): ReplayBlock & { readonly form: ReplayForm } {
    const free = { across: bar.right - bar.left, down: bar.bottom - bar.top };
    const arrangements = REPLAY_COLUMNS.map((columns) =>
        replayColumnArrangement(room, free, columns),
    );
    function inLowerHalf({ height }: { readonly height: number }): boolean {
        return height <= free.down / 2;
    }
    const pick = arrangements.reduce((best, next) =>
        next.side > best.side ||
        (next.side === best.side && !inLowerHalf(best) && inLowerHalf(next))
            ? next
            : best,
    );
    const top = bar.bottom - pick.height;
    const left = (bar.left + bar.right - pick.width) / 2;
    return {
        form: barReplayForm(pick.columns),
        rect: { bottom: bar.bottom, left, right: left + pick.width, top },
        side: pick.side,
        width: pick.width,
    };
}

/** The furiten mark's height at a tier's text (px). */
function furitenHeight({ text }: TierChrome): number {
    return FURITEN_EMS * Math.max(FURITEN_TEXT_MIN, text);
}

/**
 * A tier's named play switch is as wide as its label at this share of its switch's text, its width in the label's ems
 * fixed by that pair; a label shows only at `SWITCH_NAME_FLOOR` (px) and `SWITCH_NAME_LEAST_SHARE` of the board's text
 * or larger, and the bars are held wide enough for it where the own tile keeps its share.
 */
const SWITCH_NAME_SHARE = 0.64;
const SWITCH_NAME_FLOOR = 14;
const SWITCH_NAME_LEAST_SHARE = 0.75;

/** A notice's text is this share of the board's, never under this size (px); a phone's field is at least this many ems wide. */
const NOTICE_TEXT_SHARE = 0.92;
const NOTICE_TEXT_MIN = 11;
const NOTICE_FIELD_EMS = 7.5;

/** A desktop's notices stand as one-line toasts whose text is the board's share, never under this size (px). */
const TOAST_TEXT_MIN = 14;

/** A side strip's line shifted under the counters ends this far over a pill's height above the own tiles' foot (px). */
const LINE_PLATE_GAP = 2;

/** The cog stands centred within this many river tiles off the table column, however wide the bar. */
const BAR_REACH_RIVER_TILES = 6;

/**
 * The least bar the table column leaves a tier that names its switches: their width at the least label `namedSwitches`
 * shows and a bar's gaps, to a whole pixel; 0 off a tier that names none (px).
 */
function namedSwitchesBar({ switchLabelW, switchText, text }: TierChrome): number {
    if (switchLabelW <= 0) {
        return 0;
    }
    const label = Math.max(SWITCH_NAME_FLOOR, SWITCH_NAME_LEAST_SHARE * text);
    return Math.ceil((switchLabelW * label) / (SWITCH_NAME_SHARE * switchText)) + 2 * BAR_GAP;
}

/**
 * The play switches named where the bar holds one: the label at the board's text (the plates'), smaller to fit the bar,
 * never under `SWITCH_NAME_FLOOR` nor `SWITCH_NAME_LEAST_SHARE` of that text, so a larger board never names them
 * smaller; null where the tier shows letters or the bar holds no label that large.
 */
function namedSwitches(
    tier: TierChrome,
    barWidth: number,
): Readonly<Record<"text" | "width", number>> | null {
    if (tier.switchLabelW <= 0) {
        return null;
    }
    const ems = tier.switchLabelW / (SWITCH_NAME_SHARE * tier.switchText);
    const text = Math.min(tier.text, barWidth / ems);
    const least = Math.max(SWITCH_NAME_FLOOR, SWITCH_NAME_LEAST_SHARE * tier.text);
    return text >= least ? { text, width: text * ems } : null;
}

/** A notice's text: the board's share, small enough that the field is `ems` wide, never under the floor. */
function noticeText(text: number, fieldWidth: number, ems = NOTICE_FIELD_EMS): number {
    return Math.max(NOTICE_TEXT_MIN, Math.min(NOTICE_TEXT_SHARE * text, fieldWidth / ems));
}

/**
 * Where a barless desktop's play switches, furiten mark and field stand: `rect`, from the field's top to the switches'
 * foot, the switches centred across it (the left lane's) or at its left (the pocket's).
 */
interface BarlessStack {
    readonly rect: BoardRect;
    readonly centred: boolean;
}

/**
 * A barless desktop's stack: at the corner the left lane within its gaps, from the field under the counters
 * (`fieldTop`) to the switches' foot over the own row's plate foot (`switchesFoot`); in the pocket the pocket
 * (`pocketRect`).
 */
function barlessStack(
    { at }: ShellRoom,
    arrangement: Exclude<DesktopArrangement, "bars">,
    { fieldTop, switchesFoot }: Readonly<Record<"fieldTop" | "switchesFoot", number>>,
): BarlessStack {
    if (arrangement === "pocket") {
        return { centred: false, rect: pocketRect(at) };
    }
    const colLeft = at("col-left");
    return {
        centred: true,
        rect: {
            bottom: switchesFoot,
            left: colLeft + BAR_GAP,
            right: colLeft + BAR_GAP + laneSwitchesRoom(at("rw")),
            top: fieldTop,
        },
    };
}

/**
 * A barless desktop's controls, standing over the table: the cog at the right lane's
 * top; in the stack (`barlessStack`, the left lane's foot or the pocket) the play switches (`barlessSwitches`) at its
 * foot and the furiten mark over them, a replay's status in the field above, the side lines ending above the lane's
 * stack (`laneFootTop`) or at the own row; a replay's controls in the band's row (the layout keeps a board barless only
 * where a replay's band holds one), else in the right lane's foot under its line; and the felt edge to edge.
 */
function desktopLaneControls(
    room: ShellRoom,
    decisions: ReturnType<typeof desktopActions>,
    {
        linesEnd,
        stack,
    }: {
        readonly linesEnd: number;
        readonly stack: BarlessStack;
    },
): ReturnType<typeof desktopBars> {
    const { at, frame, tier } = room;
    const { height, width } = frame.box;
    const rw = at("rw");
    const lane = sideLane(rw);
    const colRight = at("col-right");
    const rightLane = { left: colRight - lane + BAR_GAP, right: colRight - BAR_GAP };
    const { rect } = stack;
    const across = { left: rect.left, right: rect.right };
    const switches = barlessSwitches(tier, rect.right - rect.left);
    const switchesLeft = stack.centred ? (rect.left + rect.right - switches.width) / 2 : rect.left;
    const switchesFoot = rect.bottom;
    const switchesTop = switchesFoot - switches.height;
    const furitenBottom = switchesTop - FURITEN_GAP;
    const furiten = {
        ...across,
        bottom: furitenBottom,
        top: furitenBottom - furitenHeight(tier),
    };
    const field = { ...across, bottom: furiten.top - FURITEN_GAP, top: rect.top };
    const replaying = frame.slots.band === "replay";
    const row = replayRow(room, decisions.rect);
    const replay =
        row === null
            ? replayColumn(room, {
                  ...rightLane,
                  bottom: at("hand-top") + at("oh"),
                  top: linesEnd + STRIP_ROOM_GAP,
              })
            : { ...row, form: "row" as const };
    const actions = replaying ? replay.rect : decisions.rect;
    const replayPanel: [string, number][] =
        replaying && row !== null
            ? [["overlay-bottom", height - replay.rect.top + PANEL_GAP + at("table-below")]]
            : [];
    const corner = { ...rightLane, bottom: height, top: BAR_GAP };
    return {
        areas: {
            actions,
            corner,
            field,
            furiten,
            switches: {
                bottom: switchesFoot,
                left: switchesLeft,
                right: switchesLeft + switches.width,
                top: switchesTop,
            },
        },
        cogLeft: (corner.left + corner.right - at("menu-size")) / 2,
        felt: { left: -PAGE_GUTTER, right: width + PAGE_GUTTER },
        lengths: [
            ["actions-bottom", actions.bottom],
            ["actions-left", actions.left],
            ["actions-right", width - actions.right],
            ["notice-text", Math.max(TOAST_TEXT_MIN, NOTICE_TEXT_SHARE * tier.text)],
            ["replay-b", replay.side],
            ["replay-gap", tier.replayGap],
            ["replay-group-gap", REPLAY_GROUP_GAPS * tier.replayGap],
            ["replay-w", replay.width],
            ...replayPanel,
        ],
        replay: replay.form,
        sideNameRail: null,
        switches: switches.form,
    };
}

/**
 * A desktop's controls: in the left bar the field under the counters (`fieldTop`) a clear gap off the left strip, where
 * a replay's status stands, reserving nothing (the notices stand as toasts, `desktopToasts`), the
 * furiten mark, and the play switches' column ending at `switchesFoot`
 * (a pill's height over the own tiles' foot), each switch named where the bar holds a named one at its label's floor; in the right bar the
 * cog at its top, centred on the bar's part next to the column, and where it stands (its left); over the own row live
 * play's decisions' cluster (`desktopActions`) or a replay's controls along that band's foot (`replayRow`), a replay's
 * panel standing above them, where the band holds them at the control floor, else at the right bar's foot
 * (`replayColumn`); and the felt, which meets both bars' inner edges, so every bar's control stands on the surround.
 */
function desktopBars(
    room: ShellRoom,
    decisions: ReturnType<typeof desktopActions>,
    { fieldTop, switchesFoot }: { readonly fieldTop: number; readonly switchesFoot: number },
): ControlSlots & {
    readonly cogLeft: number;
    readonly felt: Readonly<Record<"left" | "right", number>>;
} {
    const { at, frame, tier } = room;
    const { height, width } = frame.box;
    const colLeft = at("col-left");
    const colRight = at("col-right");
    const rowLine = at("hand-top") + at("oh");
    const leftBar = {
        bottom: switchesFoot,
        left: BAR_GAP,
        right: colLeft - BAR_GAP,
        top: BAR_GAP,
    };
    const rightBar = {
        bottom: rowLine,
        left: colRight + BAR_GAP,
        right: width - BAR_GAP,
        top: BAR_GAP,
    };
    const named = namedSwitches(tier, leftBar.right - leftBar.left);
    const switchesW = named === null ? tier.switchH : named.width;
    const switchesH =
        named === null
            ? SWITCH_CHIPS * tier.switchH
            : rowWidth(LABELLED_SWITCHES, tier.switchH, tier.chipGap);
    const spareWidth = leftBar.right - switchesW;
    const centredLeft = (leftBar.left + spareWidth) / 2;
    const switchesLeft = Math.max(0, Math.min(centredLeft, spareWidth - BAR_GAP));
    const furitenBottom = leftBar.bottom - switchesH - FURITEN_GAP;
    const furiten = { ...leftBar, bottom: furitenBottom, top: furitenBottom - furitenHeight(tier) };
    const field = {
        ...leftBar,
        bottom: furiten.top - FURITEN_GAP,
        right: fieldRight(colLeft),
        top: fieldTop,
    };
    const nearRight = Math.min(rightBar.right, rightBar.left + BAR_REACH_RIVER_TILES * at("rw"));
    const replaying = frame.slots.band === "replay";
    const row = replayRow(room, decisions.rect);
    const inRow = row !== null;
    const replay =
        row === null
            ? replayColumn(room, {
                  ...rightBar,
                  right: nearRight,
                  top: BAR_GAP + at("menu-size") + BAR_GAP,
              })
            : { ...row, form: "row" as const };
    const actions = replaying ? replay.rect : decisions.rect;
    const replayPanel: [string, number][] =
        replaying && inRow
            ? [["overlay-bottom", height - replay.rect.top + PANEL_GAP + at("table-below")]]
            : [];
    const namedLengths: [string, number][] =
        named === null
            ? []
            : [
                  ["switch-label-w", named.width],
                  ["switch-name-text", named.text],
              ];
    return {
        areas: {
            actions,
            corner: { ...rightBar, bottom: height, right: nearRight },
            field,
            furiten,
            switches: {
                ...leftBar,
                left: switchesLeft,
                right: switchesLeft + switchesW,
                top: leftBar.bottom - switchesH,
            },
        },
        cogLeft: (rightBar.left + nearRight - at("menu-size")) / 2,
        felt: { left: leftBar.right, right: rightBar.left },
        lengths: [
            ["actions-bottom", actions.bottom],
            ["actions-left", actions.left],
            ["actions-right", width - actions.right],
            ["notice-text", Math.max(TOAST_TEXT_MIN, NOTICE_TEXT_SHARE * tier.text)],
            ["replay-b", replay.side],
            ["replay-gap", tier.replayGap],
            ["replay-group-gap", REPLAY_GROUP_GAPS * tier.replayGap],
            ["replay-w", replay.width],
            ...replayPanel,
            ...namedLengths,
        ],
        replay: replay.form,
        sideNameRail: {
            bottom: Math.min(furiten.top, inRow ? height : replay.rect.top),
            left: 0,
            right: Math.min(leftBar.right, width - rightBar.left),
            top: Math.max(fieldTop, BAR_GAP + at("menu-size")),
        },
        switches: named === null ? "letters" : "names",
    };
}

/** A phone replay's options: the round list and the tools. */
const REPLAY_OPTIONS_ON_PHONE = 2;

function phoneReplayBlock(
    { movesH, replayGap }: Pick<TierChrome, "movesH" | "replayGap">,
    room: number,
): Readonly<Record<"columns" | "height" | "width", number>> {
    function block(columns: number): Readonly<Record<"columns" | "height" | "width", number>> {
        const rows =
            Math.ceil(REPLAY_MOVES_ON_PHONE / columns) +
            Math.ceil(REPLAY_OPTIONS_ON_PHONE / columns);
        return {
            columns,
            height: rows * movesH + (rows - 2 + REPLAY_GROUP_GAPS) * replayGap,
            width: columns * movesH + (columns - 1) * replayGap,
        };
    }
    const one = block(1);
    return one.height <= room ? one : block(2);
}

/**
 * A phone replay's controls where `phoneReplayPlace` stands them, standing on their room's foot at `right`: their box,
 * form and width (px).
 */
function phoneReplayColumn(
    { block, room }: ReturnType<typeof phoneReplayPlace>,
    right: number,
): { readonly form: ReplayForm; readonly rect: BoardRect; readonly width: number } {
    const left = right - block.width;
    return {
        form: barReplayForm(block.columns),
        rect: { bottom: room.bottom, left, right, top: room.bottom - block.height },
        width: block.width,
    };
}

/** A phone's notices' field is at least this tall where the play switches stand in a column (px): two lines of its least text. */
const PHONE_FIELD_LEAST =
    2 * Math.ceil(1.3 * NOTICE_TEXT_MIN) + 2 * Math.ceil(0.3 * NOTICE_TEXT_MIN);

/**
 * A phone's play switches: at the left rail's foot by the screen's edge, as the thumb holds the board, the two-by-two
 * block where the rail (to `railRight`) holds it, else a column where that leaves the notices' field over the furiten
 * mark `PHONE_FIELD_LEAST` tall under `fieldTop`; else the block at the left bar's foot above the own row, at `lineEnd`,
 * at the felt's edge. Their columns and box (px).
 */
function phoneSwitches({
    fieldTop,
    lineEnd,
    m,
    railFoot,
    railRight,
    switchH,
}: Readonly<
    Record<"fieldTop" | "lineEnd" | "m" | "railFoot" | "railRight" | "switchH", number>
>): Readonly<Record<"bottom" | "columns" | "left" | "top", number>> {
    const blockRows = SWITCH_CHIPS / PHONE_SWITCH_COLUMNS;
    const blockWidth = PHONE_SWITCH_COLUMNS * switchH;
    if (railRight - m >= blockWidth) {
        return {
            bottom: railFoot,
            columns: PHONE_SWITCH_COLUMNS,
            left: m,
            top: railFoot - blockRows * switchH,
        };
    }
    const columnTop = railFoot - SWITCH_CHIPS * switchH;
    if (
        railRight - m >= switchH &&
        columnTop - 2 * FURITEN_GAP - FURITEN_H - fieldTop >= PHONE_FIELD_LEAST
    ) {
        return {
            bottom: railFoot,
            columns: 1,
            left: m,
            top: columnTop,
        };
    }
    const foot = Math.max(m, lineEnd);
    return {
        bottom: foot,
        columns: PHONE_SWITCH_COLUMNS,
        left: m,
        top: foot - blockRows * switchH,
    };
}

/**
 * A phone's counters at the felt's top-left corner, at the larger dora of two places, inside it from its edge (`m` in)
 * and straddling the edge, each at most the chrome's wanted and ending at `barRight`, short of the left strip; inside
 * where both are as large, straddling centred on the edge where the margin and `barRight` allow (px).
 */
function phoneCounters({
    barRight,
    feltLeft,
    m,
    rw,
}: Readonly<Record<"barRight" | "feltLeft" | "m" | "rw", number>>): {
    readonly counters: Counters;
    readonly left: number;
} {
    const wanted = phoneChrome(rw).doraW;
    const insideLeft = feltLeft + m;
    const inside = doraFitting({ room: barRight - insideLeft, wanted });
    const straddling = doraFitting({ room: barRight - m, wanted });
    if (inside >= straddling) {
        return { counters: countersAt(inside), left: insideLeft };
    }
    const counters = countersAt(straddling);
    return {
        counters,
        left: Math.max(m, Math.min(feltLeft - counters.width / 2, barRight - counters.width)),
    };
}

/**
 * A phone's controls in the rails beside its felt and the bars beside the table column. The left side: the counters at
 * the felt's top-left corner (`phoneCounters`), the play switches at the rail's foot (`phoneSwitches`), and the furiten
 * mark and the notices' field between them, reaching over the felt's edge to short of the left strip. The right rail:
 * the cog at its top and a replay's controls (`phoneReplayColumn`) at its foot, or at the right bar's foot above the own
 * row (`phoneReplayPlace`), a replay's panel clear of them; over a panel the notices keep their field, over it. Live play's decisions stand in a band along the own row's top (`phoneActions`), as a desktop's:
 * from short of the left strip's lane to short of the right one's, 4px under the centre and so the right river's first
 * tiles (its row starts level with the centre's bottom) and 4px over the own row, their controls wrapping up from its
 * bottom right over the own river and the plates; its bottom row passes under the left river's longest reach (its last
 * tile's box), else the band starts at the centre's left edge.
 */
function phoneControls(room: ShellRoom): ControlSlots {
    const { at, frame, tier } = room;
    const { height, width } = frame.box;
    const m = at("m");
    const replaying = frame.slots.band === "replay";
    const [feltLeft, feltRight] = [at("felt-left"), at("felt-right")];
    const lanesBeside = at("lines-end") >= height - m - 0.001;
    const leftBarRight = at("col-left") - FIELD_GAP;
    const railFoot = height - m;
    const place = phoneReplayPlace({
        beside: lanesBeside,
        chrome: { ...tier, m },
        feltRight,
        height,
        lineEnd: at("lines-end"),
        rw: at("rw"),
        width,
    });
    const widestControl = Math.max(menuSize(at("rw")), place.inRail ? place.block.width : 0);
    const rightRail = {
        left: Math.min(feltRight + RAIL_GAP, width - m - widestControl),
        right: width - m,
    };
    const replay = phoneReplayColumn(place, width - m);
    const band = phoneActions(at);
    const actions = replaying ? replay.rect : band;
    const counters = phoneCounters({
        barRight: leftBarRight,
        feltLeft,
        m,
        rw: at("rw"),
    });
    const fieldTop = m + counters.counters.height + FIELD_GAP;
    const switches = phoneSwitches({
        fieldTop,
        lineEnd: at("lines-end"),
        m,
        railFoot,
        railRight: feltLeft - RAIL_GAP,
        switchH: tier.switchH,
    });
    const blockRight = switches.left + switches.columns * tier.switchH;
    const furitenBottom = switches.top - FURITEN_GAP;
    const furitenLeft = Math.max(m, (switches.left + blockRight - FURITEN_RESERVE) / 2);
    const field = {
        bottom: furitenBottom - FURITEN_H - FURITEN_GAP,
        left: m,
        right: leftBarRight,
        top: fieldTop,
    };
    const panelRight = replaying
        ? width - Math.min(feltRight, replay.rect.left) + PANEL_GAP
        : at("overlay-right");
    return {
        areas: {
            actions,
            corner: { bottom: height, left: rightRail.left, right: rightRail.right, top: m },
            field,
            furiten: {
                bottom: furitenBottom,
                left: furitenLeft,
                right: Math.min(leftBarRight, furitenLeft + FURITEN_RESERVE),
                top: furitenBottom - FURITEN_H,
            },
            switches: {
                bottom: switches.bottom,
                left: switches.left,
                right: blockRight,
                top: switches.top,
            },
        },
        lengths: [
            ...countersLengths(counters.counters, { left: counters.left, top: m }),
            ["actions-bottom", actions.bottom],
            ["actions-left", actions.left],
            ["actions-right", width - actions.right],
            ["decision-bottom", band.bottom],
            ["decision-top", band.top],
            ["field-height", Math.max(0, field.bottom - field.top)],
            ["notice-text", noticeText(tier.text, field.right - field.left)],
            ["replay-b", tier.movesH],
            ["replay-gap", tier.replayGap],
            ["replay-group-gap", REPLAY_GROUP_GAPS * tier.replayGap],
            ["overlay-right", panelRight],
            ["replay-w", replay.width],
        ],
        replay: replay.form,
        sideNameRail: {
            bottom: replaying ? replay.rect.top : furitenBottom - FURITEN_H,
            left: 0,
            right: Math.min(feltLeft, width - feltRight),
            top: m + Math.max(counters.counters.height, menuSize(at("rw"))),
        },
        switches: switches.columns === 1 ? "letters" : "block",
    };
}

/**
 * A plate keeps this far off the centre, a river's reserve and a side strip's lane (px).
 */
const PLATE_GAP = 6;

/** A plate's box is at least the control floor tall so a replay's plate is a whole target (px). */
const PLATE_TAP_FLOOR = 40;

/** A plate's box: its pill, at least `PLATE_TAP_FLOOR` tall. */
function plateBoxHeight({ pillH }: Pick<TierChrome, "pillH">): number {
    return Math.max(pillH, PLATE_TAP_FLOOR);
}

/**
 * A desktop's dora tile is this share of the river tile where its place holds it, never under the least; the counters
 * hold five indicators edge to edge in one row.
 */
const DORA_BY_RIVER_WANTED = 0.8;
const DORA_BY_RIVER_LEAST = 0.6;
const DORA_SLOTS = 5;

/** The air a desktop's counters keep off the top strip's line over the left strip's lane, in river tiles. */
const COUNTERS_AIR_BY_RIVER = 0.8;

/** The counters' padding, in dora tiles. */
const COUNTERS_PAD_BY_DORA = 0.2;

/** The counters at a dora tile: the indicators' rows on a padded card (px). */
interface Counters {
    readonly dora: number;
    readonly height: number;
    readonly pad: number;
    readonly width: number;
}

/** The counters at a dora tile, their one row's edge inside the padding (px). */
function countersAt(dora: number): Counters {
    const pad = COUNTERS_PAD_BY_DORA * dora;
    return {
        dora,
        height: 2 * pad + dora * TILE_ASPECT * LYING_Y_SHARE + TILE_EDGE_SHARE * dora,
        pad,
        width: 2 * pad + DORA_SLOTS * dora,
    };
}

/** The largest whole indicator, at most `wanted`, whose counters stand `room` wide (px). */
function doraFitting({ room, wanted }: Readonly<Record<"room" | "wanted", number>>): number {
    return Math.min(wanted, Math.floor(room / (DORA_SLOTS + 2 * COUNTERS_PAD_BY_DORA)));
}

/** The counters' lengths the stylesheet draws them with, their box's top left corner at `left` and `top` (px). */
function countersLengths(
    counters: Counters,
    { left, top }: Readonly<Record<"left" | "top", number>>,
): [string, number][] {
    return [
        ["counters-h", counters.height],
        ["counters-top", top],
        ["counters-w", counters.width],
        ["counters-x", left],
        ["dora-pad", counters.pad],
        ["dora-w", counters.dora],
    ];
}

/** The counters' lengths, the field's top under them and the floor the side strips' lines start at (px). */
interface DesktopCounters {
    readonly counters: readonly [string, number][];
    readonly fieldTop: number;
    readonly linesFloor: number;
    readonly right: number;
}

/**
 * A desktop's counters at the table's top-left corner, level with the top hand's top (px). Over the left strip's lane
 * (`place`) they end a plate's gap short of the lane's inner edge, beside the top strip's line, in one row of five
 * indicators `DORA_BY_RIVER_WANTED` of a river tile, smaller to fit the room from the bar's edge, never under
 * `DORA_BY_RIVER_LEAST`, the side strips' lines starting under them (`linesFloor`); in the bar they end at its edge by
 * the left strip. Shrunk, where neither holds the row at the least (`linesStart` where the side lines start), they keep
 * one row over the lane above that start where it holds the least, else in the bar at whatever indicator it holds.
 */
function desktopCounters({
    cog = 0,
    colLeft,
    linesStart = 0,
    place,
    rw,
}: {
    readonly cog?: number;
    readonly colLeft: number;
    readonly linesStart?: number;
    readonly place: CountersPlace;
    readonly rw: number;
}): DesktopCounters {
    const least = leastDora(rw);
    const wanted = Math.max(least, Math.floor(DORA_BY_RIVER_WANTED * rw));
    if (place === "corner") {
        const counters = countersAt(wanted);
        return {
            counters: countersLengths(counters, { left: colLeft + BAR_GAP, top: 0 }),
            fieldTop: counters.height + BAR_GAP,
            linesFloor: Math.max(counters.height, BAR_GAP + cog) + PLATE_GAP,
            right: colLeft + BAR_GAP + counters.width,
        };
    }
    const barEdge = fieldRight(colLeft);
    const overLane = laneEdge(colLeft, rw);
    const edgesByPlace: Readonly<Record<Exclude<CountersPlace, "corner">, readonly number[]>> = {
        bar: [barEdge],
        lane: [overLane],
        shrunk: [barEdge, overLane],
    };
    const places = edgesByPlace[place].map((edge) => ({
        counters: countersAt(doraFitting({ room: edge - BAR_GAP, wanted })),
        edge,
    }));
    const { counters, edge } =
        places.find(
            (candidate) =>
                candidate.counters.dora >= least &&
                (place !== "shrunk" ||
                    candidate.edge <= barEdge ||
                    candidate.counters.height + PLATE_GAP <= linesStart),
        ) ?? places[0];
    const left = Math.max(BAR_GAP, edge - counters.width);
    return {
        counters: countersLengths(counters, { left, top: 0 }),
        fieldTop: counters.height + BAR_GAP,
        linesFloor: place === "lane" ? counters.height + PLATE_GAP : 0,
        right: left + counters.width,
    };
}

/**
 * Where a desktop's counters stand, from its arrangement and lengths: at the corner on a barless board, whichever its
 * arrangement; else over the lane where the side strips' lines start below them, else in the bar where it holds their
 * one row, else shrunk.
 */
function desktopCountersPlace({ at }: ShellRoom, arrangement: DesktopArrangement): CountersPlace {
    const rw = at("rw");
    const colLeft = at("col-left");
    if (arrangement !== "bars") {
        return "corner";
    }
    if (
        countersHold({ colLeft, place: "lane", rw }) &&
        at("lines-start") >= desktopCounters({ colLeft, place: "lane", rw }).linesFloor - 0.001
    ) {
        return "lane";
    }
    return countersHold({ colLeft, place: "bar", rw }) ? "bar" : "shrunk";
}

/** Where a plate's box would stand with its pill's foot level with the own tiles', within the table (px). */
function rowFootPlateTop({ at, frame, tier }: ShellRoom): number {
    return plateTopAtRowFoot({
        handTop: at("hand-top"),
        height: frame.box.height,
        oh: at("oh"),
        tier,
    });
}

function plateTopAtRowFoot({
    handTop,
    height,
    oh,
    tier,
}: Readonly<Record<"handTop" | "height" | "oh", number>> & { readonly tier: TierChrome }): number {
    const pad = (plateBoxHeight(tier) - tier.pillH) / 2;
    return Math.min(handTop + oh - tier.pillH - pad, height - plateBoxHeight(tier));
}

/**
 * The play switches in a barless desktop's room `width` wide (the left lane's within its gaps, or the pocket's): two by
 * two where it holds the block, else the letters' column.
 */
function barlessSwitches(
    tier: TierChrome,
    width: number,
): Readonly<{ form: SwitchesForm; height: number; width: number }> {
    if (2 * tier.switchH <= width) {
        return { form: "block", height: 2 * tier.switchH, width: 2 * tier.switchH };
    }
    return { form: "letters", height: SWITCH_CHIPS * tier.switchH, width: tier.switchH };
}

/** The left lane's room for a barless desktop's play switches: the lane within a bar's gap on each side (px). */
function laneSwitchesRoom(rw: number): number {
    return sideLane(rw) - 2 * BAR_GAP;
}

/**
 * A pocket desktop's free upper-left pocket: past the left strip's lane, short of the top river's run-on third row and
 * the centre, below the top strip's painted foot (its edge included) and above the left river, a plate's gap off each
 * (px).
 */
function pocketRect(at: (name: string) => number): BoardRect {
    const rw = at("rw");
    return {
        bottom: at("cy") - at("h") - PLATE_GAP,
        left: at("col-left") + sideLane(rw) + PLATE_GAP,
        right: Math.min(at("reach-top-left"), at("cx") - at("hx")) - PLATE_GAP,
        top: at("m") + (STACKED_DEPTH * LYING_Y_SHARE + TILE_EDGE_SHARE) * rw + PLATE_GAP,
    };
}

/**
 * Whether a pocket holds its stack: the play switches as wide as it lets them (`barlessSwitches`) within its width, and
 * they, the furiten mark and its gaps short of its height, so the field above them keeps some.
 */
function pocketHolds(tier: TierChrome, pocket: BoardRect): boolean {
    const width = pocket.right - pocket.left;
    const switches = barlessSwitches(tier, width);
    return (
        switches.width <= width &&
        switches.height + 2 * FURITEN_GAP + furitenHeight(tier) < pocket.bottom - pocket.top
    );
}

/**
 * Where a barless desktop's left lane foot starts: the play switches ending a gap over the own row's plate foot, the
 * furiten mark over them; the side strips' lines end above it (px).
 */
function laneFootTop({
    handTop,
    height,
    oh,
    rw,
    tier,
}: Readonly<Record<"handTop" | "height" | "oh" | "rw", number>> & {
    readonly tier: TierChrome;
}): number {
    const switchesFoot = plateTopAtRowFoot({ handTop, height, oh, tier }) - BAR_GAP;
    return (
        switchesFoot -
        barlessSwitches(tier, laneSwitchesRoom(rw)).height -
        FURITEN_GAP -
        furitenHeight(tier) -
        FURITEN_GAP
    );
}

/** The own row's area from `start` to `end` and the lengths it is placed by, its foreground from `lineEnd` down. */
function ownRowSlot(
    at: (name: string) => number,
    { end, lineEnd, start }: Readonly<Record<"end" | "lineEnd" | "start", number>>,
): { readonly area: BoardRect; readonly lengths: readonly [string, number][] } {
    const handTop = at("hand-top");
    return {
        area: { bottom: handTop + at("oh"), left: start, right: end, top: handTop },
        lengths: [
            ["foreground-top", lineEnd],
            ["own-row-w", end - start],
            ["own-start", start],
        ],
    };
}

/**
 * A desktop's notices' place, their toasts stacked as lines: the core's bottom-left corner, past the left strip's lane
 * to short of the bottom river's first tile, under the left river's longest reach and over the own row's melds' rise,
 * where no tile or control reaches; they stand over the left plate (px).
 */
function desktopToasts(room: ShellRoom): BoardRect {
    const { at } = room;
    const rw = at("rw");
    return {
        bottom: at("hand-top") - at("own-meld-rise") - ACTIONS_GAP,
        left: at("col-left") + sideLane(rw) + ACTIONS_GAP,
        right: at("cx") - at("hx") - ACTIONS_GAP,
        top: at("cy") + leftRiverReach(rw, at("latest-drop-gap")) + TOASTS_RIVER_GAP,
    };
}

/**
 * A desktop's slots: the opponents' strips, the own row between the side strips' lanes centred on the core, the
 * controls as its arrangement puts them, in the bars (`desktopBars`) or over the table (`desktopLaneControls`), under
 * the counters (`desktopCounters`), the decisions in a band along the own row's top (`desktopActions`), the notices in
 * the core's bottom-left corner (`desktopToasts`).
 */
function desktopShell(room: ShellRoom, arrangement: DesktopArrangement): BoardShell {
    const { at } = room;
    const lane = sideLane(at("rw"));
    const halfRow = (FULL_HAND * at("ow")) / 2;
    const ownStart = Math.max(at("col-left") + lane, at("cx") - halfRow);
    const ownEnd = Math.min(at("col-right") - lane, at("cx") + halfRow);
    const lines = desktopSideLines(room);
    const place = desktopCountersPlace(room, arrangement);
    const counters = desktopCounters({
        cog: at("menu-size"),
        colLeft: at("col-left"),
        linesStart: lines.start,
        place,
        rw: at("rw"),
    });
    const decisions = desktopActions(room);
    const placed = {
        fieldTop: counters.fieldTop,
        switchesFoot: rowFootPlateTop(room) - BAR_GAP,
    };
    const controls =
        arrangement === "bars"
            ? desktopBars(room, decisions, placed)
            : desktopLaneControls(room, decisions, {
                  linesEnd: lines.end,
                  stack: barlessStack(room, arrangement, placed),
              });
    const strips = opponentStrips(room, {
        leftEnd: lines.end,
        leftStart: lines.start,
        lineClear: STRIP_ROOM_GAP,
        ownStart,
        rightEnd: lines.end,
        rightStart: lines.start,
        topEnd: Math.min(topHandEnd(at), controls.cogLeft - PLATE_GAP),
        topStart: place === "corner" ? counters.right + FIELD_STRIP_GAP : undefined,
    });
    const own = ownRowSlot(at, {
        end: ownEnd,
        lineEnd: sideLineEnd(at("hand-top"), at("own-meld-rise"), STRIP_ROOM_GAP),
        start: ownStart,
    });
    const toasts = desktopToasts(room);
    return {
        areas: { ...controls.areas, hand: own.area, ...strips.areas, toasts },
        lengths: [
            ...controls.lengths,
            ["felt-left", controls.felt.left],
            ["felt-right", controls.felt.right],
            ...counters.counters,
            ...own.lengths,
            ["decision-bottom", decisions.rect.bottom],
            ["decision-top", decisions.rect.top],
            ["toasts-height", toasts.bottom - toasts.top],
            ["toasts-left", toasts.left],
            ["toasts-top", toasts.top],
            ["toasts-w", toasts.right - toasts.left],
        ],
        replay: controls.replay,
        sideNameRail: controls.sideNameRail,
        strips: strips.strips,
        switches: controls.switches,
    };
}

/**
 * A phone's slots: the side strips at the table column's
 * edges, their lines from the top margin to the bars' foot, the top one between their lanes; the own row in the felt,
 * from a full hand centred on the board to the felt's air short of its right edge under both lanes, or between them
 * where they stand beside it; and the controls in the rails and bars and the decisions' band over the own row
 * (`phoneControls`).
 */
function phoneShell(room: ShellRoom): BoardShell {
    const { at } = room;
    const m = at("m");
    const ownStart = at("own-start");
    const lineEnd = at("lines-end");
    const strips = opponentStrips(room, {
        leftEnd: lineEnd,
        leftStart: m,
        lineClear: STRIP_CONTROL_CLEAR,
        ownStart,
        rightEnd: lineEnd,
        rightStart: m,
        topEnd: topHandEnd(at),
    });
    const controls = phoneControls(room);
    const own = ownRowSlot(at, { end: at("own-end"), lineEnd, start: ownStart });
    return {
        areas: { ...controls.areas, hand: own.area, ...strips.areas },
        lengths: [...controls.lengths, ...own.lengths],
        replay: controls.replay,
        sideNameRail: controls.sideNameRail,
        strips: strips.strips,
        switches: controls.switches,
    };
}

/** What every family's board reads alike: an opponent's drawn tile's gaps and full reach, and a side strip's stacked depth. */
function stripFacts(rw: number): [string, number][] {
    return [
        ["dg", drawnGap(rw, "top")],
        ["side-dg", drawnGap(rw, "left")],
        ["full-reach", fullReach(rw, "left")],
        ["strip-depth", STACKED_DEPTH * rw],
    ];
}

const PHONE_PLATE_TEXT = 10;
const PLATE_EMS = 8;
const HAND_PLATE_AIR = 0.2;

/**
 * Every seat's plate stands over its own hand: a side seat's a plate's gap along from the hand's start and a gap short
 * of its lane's inner edge, where a stacked added kan reaches, the own one centred on the hand's first tile, moved off it
 * only as far as clears the left strip's reach, the top one ending where the hand starts; both with more air under them.
 * An opponent's plate is the own one turned with its seat, from the inner corner where its hand starts
 * (`plate-<seat>-x/y`); `plate-<seat>-along` and `plate-<seat>-rise` place it in that turned frame, the left one further
 * along where the top strip's corner would cover it, the right one where the own row would; the top one runs on past
 * the hand's start where the room beside the top river is narrower than the plate, short of the right strip's lane.
 */
function handPlateLengths(
    { at, frame, tier }: ShellRoom,
    { areas, lengths }: BoardShell,
): [string, number][] {
    const { hand, "strip-left": left, "strip-right": right, "strip-top": top } = areas;
    const phone = frame.family === "phone";
    const text = phone ? PHONE_PLATE_TEXT : tier.text;
    const wanted = PLATE_EMS * text;
    const height = plateBoxHeight(tier);
    const reservedPillHeight = phone ? tier.pillH * 0.7 : tier.pillH;
    const pillHeight = phone ? reservedPillHeight * 0.7 : reservedPillHeight;
    const pillFoot = (height + pillHeight) / 2;
    const clearance = Math.ceil(pillFoot + PLATE_GAP);

    const air = Math.max(PLATE_GAP, Math.round(HAND_PLATE_AIR * at("rw")));
    const ownRowTop = Math.floor(hand.top - at("own-meld-rise"));
    const ownStart = lengths.find(([name]) => name === "own-start")?.[1] ?? hand.left;
    const ownX = Math.max(ownStart + (at("ow") - wanted) / 2, left.right + PLATE_GAP);
    const ownY = ownRowTop - clearance - air;
    const sideDepth = STACKED_DEPTH * at("rw");
    const topFoot = (TILE_ASPECT + TOP_HAND_EDGE_SHARE) * at("rw");
    const topStart = at("cx") + at("hx") + PLATE_GAP;
    const topWidth = Math.min(wanted, right.left - PLATE_GAP - topStart);
    const topPastHand = Math.max(0, topStart + topWidth - top.right);
    const leftReach = left.left + sideDepth + clearance;
    const leftAlong =
        leftReach > top.left ? Math.max(PLATE_GAP, top.bottom + PLATE_GAP - left.top) : PLATE_GAP;
    const rightReach = right.right - sideDepth - clearance;
    const rightAlong =
        rightReach < hand.right
            ? Math.max(PLATE_GAP, right.bottom + PLATE_GAP - ownRowTop)
            : PLATE_GAP;

    const positions = {
        bottom: [ownX, ownY, wanted],
        left: [left.left + sideDepth, left.top, wanted],
        right: [right.right - sideDepth, right.bottom, wanted],
        top: [top.right, top.top + topFoot, topWidth],
    } as const;
    const places: [string, number][] = Object.entries(positions).flatMap(
        ([seat, [leftEdge, topEdge, width]]) => [
            [`plate-${seat}-x`, leftEdge],
            [`plate-${seat}-y`, topEdge],
            [`plate-${seat}-w`, width],
        ],
    );
    return [
        ...places,
        ["plate-left-along", leftAlong],
        ["plate-right-along", rightAlong],
        ["plate-top-along", -topPastHand],
        ["plate-left-rise", clearance],
        ["plate-right-rise", clearance],
        ["plate-top-rise", clearance + air],
        ["plate-text", text],
        ["plate-pill-h", pillHeight],
    ];
}

const BASE_CALL_SCALE = { gap: 1, size: 1 };
const COMPACT_CALL_SCALE = { gap: 1.5, size: 1.2 };
const FULL_CALL_SCALE = { gap: 3, size: 1.32 };
const CALL_FIT_STEPS = 20;
const CALL_BUTTON_SCALE = 0.8;
const CALL_MIN_HEIGHT = 40;

/** Fit the same buttons throughout a decision, including its widest tile picker. */
function fitCallButtons({ at, frame }: ShellRoom, band: BoardRect): [string, number][] {
    const count = frame.slots.decisionCapacity ?? 0;
    if (count === 0) {
        return [];
    }
    const baseWidth = at("action-min-w") * CALL_BUTTON_SCALE;
    const baseHeight = at("decision-h") * CALL_BUTTON_SCALE;
    const minHeight = Math.max(CALL_MIN_HEIGHT, baseHeight);
    const baseGap = at("decision-gap");
    const slots = count + 1;
    const availableWidth = band.right - band.left;
    const availableHeight = band.bottom - band.top;
    const targetHeight = baseHeight * FULL_CALL_SCALE.size;
    const widthBesideRiver = band.right - (at("cx") - at("hx"));
    const roomUnderRiver =
        frame.family === "phone"
            ? band.bottom - phoneLeftRiverEnd(at) - STRIP_CONTROL_CLEAR
            : availableHeight;
    let best = {
        gap: baseGap,
        height: minHeight,
        rowGap: baseGap,
        width: baseWidth,
    };
    for (let step = 0; step <= 2 * CALL_FIT_STEPS; step++) {
        const compact = step <= CALL_FIT_STEPS;
        const from = compact ? BASE_CALL_SCALE : COMPACT_CALL_SCALE;
        const to = compact ? COMPACT_CALL_SCALE : FULL_CALL_SCALE;
        const progress = (compact ? step : step - CALL_FIT_STEPS) / CALL_FIT_STEPS;
        const width = baseWidth * (from.size + (to.size - from.size) * progress);
        const gap = baseGap * (from.gap + (to.gap - from.gap) * progress);
        const perRow = Math.floor((availableWidth + gap) / (width + gap));
        if (perRow < 2) {
            break;
        }
        const rows = Math.ceil(slots / perRow);
        const bottomWidth = Math.min(slots, perRow) * (width + gap) - gap;
        const upperWidth = Math.min(Math.max(0, slots - perRow), perRow) * (width + gap) - gap;
        const rowRoom =
            upperWidth > widthBesideRiver
                ? Math.min(availableHeight, roomUnderRiver)
                : availableHeight;
        const bottomRoom = bottomWidth > widthBesideRiver ? roomUnderRiver : availableHeight;
        const height = Math.min(targetHeight, bottomRoom, (rowRoom - (rows - 1) * baseGap) / rows);
        if (height >= minHeight - 0.01 && height * width >= best.height * best.width) {
            const rowGap = rows === 1 ? gap : Math.min(gap, (rowRoom - rows * height) / (rows - 1));
            best = {
                gap,
                height,
                rowGap,
                width,
            };
        }
    }
    const { width, height } = best;
    return [
        ["call-w", width],
        ["call-h", height],
        ["call-gap", best.gap],
        ["call-row-gap", best.rowGap],
        ["call-text", actionText(height, width)],
    ];
}

/** A family's slots from its lengths and, off a phone, its arrangement. */
function boardShell(frame: BoardFrame, { arrangement, lengths }: LaidBoard): BoardShell {
    function at(name: string): number {
        return lengths[name] ?? 0;
    }
    const grown = grownChrome(frame.tier, chromeGrowth(frame.chrome, at("rw")));
    const tier =
        arrangement === null ? phoneChrome(at("rw")) : atDecisionScale(grown, at("decision-h"));
    const room = { at, frame, tier };
    const shell = arrangement === null ? phoneShell(room) : desktopShell(room, arrangement);
    const calls = fitCallButtons(room, shell.areas.actions);
    return {
        ...shell,
        lengths: [
            ...shell.lengths,
            ...stripFacts(at("rw")),
            ...handPlateLengths(room, shell),
            ...calls,
        ],
    };
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

function familyLengths(frame: BoardFrame): LaidBoard {
    if (frame.family === "phone") {
        return { arrangement: null, lengths: phoneLengths(frame) };
    }
    return desktopLengths(frame);
}

/** The edges a page holds around any family's board before it is known: each the larger of its safe inset and the gutter. */
function gutteredEdges({ bottom, left, right, top }: BoardEdges): BoardEdges {
    return {
        bottom: Math.max(bottom, PAGE_GUTTER),
        left: Math.max(left, PAGE_GUTTER),
        right: Math.max(right, PAGE_GUTTER),
        top: Math.max(top, PAGE_GUTTER),
    };
}

/** The edges a page holds around a phone's board: the side and top safe insets, the bottom bare to the screen's edge. */
function phoneEdges(safeInsets: BoardEdges): BoardEdges {
    return { ...safeInsets, bottom: 0 };
}

/** The measured box once the page holds `edges` in place of the ones it applies now. */
function boxUnderEdges({ appliedEdges: now, box }: BoardInput, edges: BoardEdges): BoardBox {
    return {
        height: box.height + (now.top - edges.top) + (now.bottom - edges.bottom),
        width: box.width + (now.left - edges.left) + (now.right - edges.right),
    };
}

/**
 * The board's geometry: the page's raw box under the guttered edges classified once, whatever padding the page holds
 * now, a phone taking its own edges (no gutter, the bottom bare), any other family the guttered box, and its sizes in
 * px for that box; an empty or non-finite box has no sizes.
 */
function boardGeometry(input: BoardInput): BoardGeometry {
    return solveFrame(boardFrame(input), familyLengths);
}

function boardFrame(input: BoardInput): BoardFrame {
    const candidate = boxUnderEdges(input, gutteredEdges(input.safeInsets));
    const family = classifyFamily(candidate);
    const chrome = classifyChrome(candidate);
    return {
        box: family === "phone" ? boxUnderEdges(input, phoneEdges(input.safeInsets)) : candidate,
        chrome,
        family,
        slots: input.slots,
        tier: tierChrome(chrome, chromeShare(candidate)),
    };
}

function solveFrame(frame: BoardFrame, lay: (frame: BoardFrame) => LaidBoard): BoardGeometry {
    const { box, chrome, family } = frame;
    const sized =
        Number.isFinite(box.width) &&
        Number.isFinite(box.height) &&
        box.width > 0 &&
        box.height > 0;
    const laid = sized ? lay(frame) : null;
    const sizes = laid?.lengths ?? {};
    const tableHeight = sizes["table-h"];
    const table = tableHeight === undefined ? frame : frameAtHeight(frame, tableHeight);
    const shell = laid === null ? null : boardShell(table, laid);
    return Object.freeze({
        areas: Object.freeze({ ...shell?.areas }),
        arrangement: laid?.arrangement ?? null,
        box: Object.freeze(box),
        chrome,
        family,
        gutter: family === "phone" ? 0 : PAGE_GUTTER,
        lengths: Object.freeze({
            ...sizes,
            ...Object.fromEntries(shell?.lengths ?? []),
        }),
        replay: shell?.replay ?? "column",
        strips: shell === null ? null : Object.freeze(shell.strips),
        switches: shell?.switches ?? "letters",
        tracks: Object.freeze(
            shell === null ? { columns: "", rows: "" } : shellTracks(shell.areas, table.box),
        ),
    });
}

export { boardGeometry, desktopPlanMisfits, phonePromptHeight, shellTracks };
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
    DesktopArrangement,
    DesktopMisfit,
    ReplayForm,
    SwitchesForm,
};
