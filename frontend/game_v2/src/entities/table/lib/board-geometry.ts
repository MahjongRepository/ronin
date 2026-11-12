import { RIVER_ROWS, RIVER_ROW_SIZE } from "@/entities/tile";

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
    PHONE_HEIGHT,
    PHONE_OWN_FLOOR,
    PHONE_OWN_TAP_FLOOR,
    type PhoneChrome,
    REGULAR_CHROME_HEIGHT,
    RIVER_GAP_SHARE,
    ROWS_BEFORE_RUN_ON,
    RUN_ON_REACH_TILES,
    SIDEWAYS_UNITS,
    SIDE_LANE_GAP,
    SIDE_REACH_TILES,
    SMALL_CHROME_WIDTH,
    STACKED_DEPTH,
    TABLE_COLUMN_TILES,
    TIER_CHROME,
    TILE_ASPECT,
    TILE_EDGE_SHARE,
    TOP_HAND_AIR,
    TOP_HAND_GAP,
    type TierChrome,
} from "./board-constants";
import { type StripRooms, type StripSeat, drawnGap, hairline, handLength } from "./strip-layout";

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
}

/** The switches step in this far past an opponent's tile height (px). */
const STEP_IN_GAP = 6;

/** The play switches' strip: three square chips and the names' button. */
const SWITCH_CHIPS = 4;

/** The play switches where they show their whole names, with no names' button. */
const LABELLED_SWITCHES = 3;

/** The replay's moves in the switches' place. */
const REPLAY_MOVES = 7;
/** The replay's options at the band's end: the viewpoint, the other hands and the round list. */
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
    TILE_EDGE_SHARE +
    TOP_HAND_GAP +
    CORE_TILES +
    2 * (DESKTOP_RIVER_GAP_SHARE - RIVER_GAP_SHARE) +
    3 * TILE_EDGE_SHARE +
    DESKTOP_CENTRE_TILES +
    OWN_ROW_GAP +
    Math.max(0, 2 * OWN_MELD_SCALE - OWN_BY_RIVER_OFF_PHONE * TILE_ASPECT) +
    OWN_BY_RIVER_OFF_PHONE * (TILE_ASPECT + TILE_EDGE_SHARE);

/**
 * The latest discard's gap along the light off a phone (px): the gap across it and the tile edge that falls into it,
 * the previous tile's on the left river and above a bottom river's row, the latest tile's own on the right river and
 * under a top river's row. A phone keeps the gap across: its edge is two pixels, and the reserve would cost it a pixel
 * of river tile at its floor.
 */
function latestDropGap(rw: number): number {
    return LATEST_DISCARD_GAP + Math.round(TILE_EDGE_SHARE * rw);
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

/** While a notice shows, a phone's live panel keeps this far off the notices' column beside it (px). */
const NOTICES_PANEL_GAP = 4;

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
function meldsReach(rw: number, { count, gap, upright }: MeldsLine): number {
    return (
        handLength({ drawn: true, rw, seat: "left", tiles: HAND_TILES - 3 * count }) +
        count * (gap + (upright + SIDEWAYS_UNITS) * FACE_FLOOR)
    );
}

interface MeldsLine {
    readonly count: number;
    readonly upright: number;
    readonly gap: number;
}

function kansReach(rw: number, count: number): number {
    return meldsReach(rw, { count, gap: riverGap(rw) + MELD_GAP_EXTRA, upright: 3 });
}

function ponsReach(rw: number): number {
    return meldsReach(rw, { count: ORDINARY_PONS, gap: riverGap(rw) + MELD_GAP_EXTRA, upright: 2 });
}

/**
 * A phone's side lanes stand above its own row where their lines hold this many open kans at the face floor, their gaps
 * closed to the tightest, reaching at most into the own row's clearance; a rarer fourth lies on past the line.
 */
const PHONE_LINE_KANS = 3;

function tightKansReach(rw: number): number {
    return meldsReach(rw, { count: PHONE_LINE_KANS, gap: MELD_GAP_TIGHT, upright: 3 });
}

/** A side strip reserves one line even for four open kans at the meld face floor. */
function sideStripReach(rw: number): number {
    return Math.max(fullReach(rw, "left"), ...RESERVED_KANS.map((count) => kansReach(rw, count)));
}

/**
 * A phone's side strip reserves its full concealed hand and as much of a four-kan line at the face floor as `room` holds
 * (a browser's bars leave a box too short for all of it): the melds of a rarer denser seat lie on past the line
 * (`stripLayout`'s overflow), never shrinking the river tile for them.
 */
function phoneSideReach(rw: number, room: number): number {
    return Math.max(fullReach(rw, "left"), Math.min(sideStripReach(rw), room));
}

/**
 * Where a side strip's line ends: `clear` above the own row and the rise its melds take (a desktop's left strip
 * `STRIP_ROOM_GAP`, a phone's both `STRIP_CONTROL_CLEAR`).
 */
function sideLineEnd(handTop: number, ownMeldRise: number, clear: number): number {
    return handTop - ownMeldRise - clear;
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
function riverRows(rw: number, gap: number): number {
    return gap + (CORE_TILES / 2 - RIVER_GAP_SHARE) * rw;
}

/**
 * The core's lengths: the centre (`cx`/`cy` its middle, `c`/`h` its height and half, `w`/`hx` its width and half), the
 * river tile, the gaps between the centre and the rivers (the top one's `g-top`), and the rivers' reserved reach, a
 * row's sideways riichi tile and the latest discard's gap counted: a side river's fourth row, a top or bottom river's
 * third row run on to eight tiles, and the top river's third row's centre-facing edge, which no gap moves toward the
 * centre; and the latest discard's gaps.
 */
function coreLengths(
    {
        cx,
        cy,
        height,
        rw,
        width,
    }: Readonly<Record<"cx" | "cy" | "height" | "rw" | "width", number>>,
    { drop, gap, topGap }: Readonly<Record<"drop" | "gap" | "topGap", number>>,
): [string, number][] {
    const hx = width / 2;
    const sideReach = (SIDE_REACH_TILES / 2) * rw + LATEST_DISCARD_GAP;
    const runOnReach = RUN_ON_REACH_TILES * rw + LATEST_DISCARD_GAP;
    return [
        ["c", height],
        ["cx", cx],
        ["cy", cy],
        ["g", gap],
        ["g-top", topGap],
        ["h", height / 2],
        ["hx", hx],
        ["latest-discard-gap", LATEST_DISCARD_GAP],
        ["latest-drop-gap", drop],
        ["reach-bottom-right", cx - hx + runOnReach],
        ["reach-left", cx - hx - gap - (SIDE_REACH_TILES / 2) * rw - LATEST_DISCARD_GAP],
        ["reach-right", cx + hx + gap + sideReach],
        ["reach-top-left", cx + hx - runOnReach],
        ["reach-top-row3", cy - height / 2 - topGap - ROWS_BEFORE_RUN_ON * rw],
        ["rh", rw * TILE_ASPECT],
        ["river-across", RIVER_ROWS["run-on"] * rw * TILE_ASPECT],
        ["river-along", RIVER_ROW_SIZE * rw],
        ["rw", rw],
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
}

/** A desktop's root sizes and the lengths the stylesheet reads with them, in px, at the largest river tile that fits. */
function desktopLengths(frame: BoardFrame): BoardLengths {
    let rw = Math.max(1, Math.floor(frame.box.height / DESKTOP_STACK_TILES));
    let layout = desktopLayout(frame, rw);
    while (rw > 1 && !fitsDesktop(layout)) {
        rw -= 1;
        layout = desktopLayout(frame, rw);
    }
    const table = widthBoundTable(frame, rw);
    if (table === null) {
        return layout.lengths;
    }
    return {
        ...desktopLayout(table, rw, fitsDrawnOwnRow).lengths,
        "table-h": table.box.height,
        "table-top": Math.floor((frame.box.height - table.box.height) / 2),
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

function widthBoundTable(frame: BoardFrame, rw: number): BoardFrame | null {
    const next = desktopLayout(frame, rw + 1);
    if (!next.tall || next.wide) {
        return null;
    }
    const { infoInRow } = desktopLayout(frame, rw);
    const height =
        leastHeight(frame, (table) => {
            const layout = desktopLayout(table, rw, fitsDrawnOwnRow);
            return fitsDrawnOwnRow(layout) && (layout.infoInRow || !infoInRow);
        }) + Math.round(TOP_HAND_AIR * rw);
    return height < frame.box.height ? frameAtHeight(frame, height) : null;
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

interface DesktopLayout {
    readonly lengths: BoardLengths;
    readonly stacked: boolean;
    readonly tall: boolean;
    readonly wide: boolean;
    readonly infoInRow: boolean;
}

/**
 * Where a desktop's counters and round info stand: in the left bar; over the left strip's lane with the side strips'
 * lines starting below them; the counters over the lane, their lines starting below them, and the info in the bar
 * under them; or the counters wrapped where none holds their one row.
 */
type InfoPlace = "bar" | "lane" | "counters-lane" | "wrap";

/** A desktop's bar and where its counters stand at it: the table's sizes solved for both. */
interface DesktopPlan {
    readonly bar: number;
    readonly info: InfoPlace;
}

/**
 * The plans a desktop tries, best first, each only where its own tile stays the share of the river tile it asks (the
 * wanted share, then the least): the play switches named, then lettered at the least bar; the counters' one row over
 * the lane with the round info where the side strips' lines can start below both, else over the lane alone, else in a
 * bar widened to hold it; the counters wrapped at the least bar last.
 */
function desktopPlans(
    tier: TierChrome,
    rw: number,
): readonly (DesktopPlan & { readonly share: number })[] {
    const named = Math.max(BAR_MIN, namedSwitchesBar(tier));
    const info = infoBar(rw);
    const bars = named > BAR_MIN ? [named, BAR_MIN] : [BAR_MIN];
    return [OWN_BY_RIVER_WANTED, OWN_BY_RIVER_LEAST].flatMap((share) =>
        bars.flatMap((bar) => [
            { bar, info: "lane" as const, share },
            { bar, info: "counters-lane" as const, share },
            { bar: Math.max(bar, info), info: "bar" as const, share },
        ]),
    );
}

function desktopLayout(
    frame: BoardFrame,
    rw: number,
    fits: (layout: DesktopLayout) => boolean = fitsDesktop,
): DesktopLayout {
    const tier = grownChrome(frame.tier, chromeGrowth(frame.chrome, rw));
    const plans = desktopPlans(tier, rw).filter(
        (plan) => desktopOwnTile({ bar: plan.bar, rw, width: frame.box.width }) >= plan.share * rw,
    );
    for (const plan of plans) {
        const layout = desktopAt(frame, rw, plan);
        if (layout.ownShare >= plan.share && layout.infoInRow && fits(layout)) {
            return layout;
        }
    }
    return desktopAt(frame, rw, { bar: BAR_MIN, info: "wrap" });
}

/**
 * The px the left bar takes to hold the counters' one row at their least indicator and the round info's lines at their
 * least text, their gaps counted.
 */
function infoBar(rw: number): number {
    return (
        BAR_GAP +
        Math.max(countersAt(leastDora(rw), DORA_SLOTS).width, leastInfo()) +
        FIELD_STRIP_GAP
    );
}

/** The round info's least width: its lines at the least text (px). */
function leastInfo(): number {
    return DESKTOP_NOTICE_FIELD_EMS * STATUS_TEXT_MIN;
}

/** The round info's least width with the round's name broken between the round and its honba (px). */
function wrappedInfo(): number {
    return STATUS_WRAPPED_EMS * STATUS_TEXT_MIN;
}

/**
 * Whether the counters' one row at their least indicator stands where `place` puts it, and the round info's lines at
 * their least text with them, or in the bar under them.
 */
function infoHolds({
    colLeft,
    place,
    rw,
}: {
    readonly colLeft: number;
    readonly place: InfoPlace;
    readonly rw: number;
}): boolean {
    const row = countersAt(leastDora(rw), DORA_SLOTS).width;
    const inBar = fieldRight(colLeft) - BAR_GAP;
    const overLane = laneEdge(colLeft, rw) - BAR_GAP;
    const holds: Readonly<Record<InfoPlace, boolean>> = {
        bar: Math.max(row, leastInfo()) <= inBar,
        "counters-lane": row <= overLane && wrappedInfo() <= inBar,
        lane: Math.max(row, leastInfo()) <= overLane,
        wrap: false,
    };
    return holds[place];
}

/** A desktop's least dora indicator (px). */
function leastDora(rw: number): number {
    return Math.ceil(DORA_BY_RIVER_LEAST * rw);
}

/** Where a desktop's counters end over the left strip's lane: a plate's gap short of the lane's inner edge (px). */
function laneEdge(colLeft: number, rw: number): number {
    return colLeft + sideLane(rw) - PLATE_GAP;
}

/** The round info's height under the counters at its text (px): its two lines, or three with the round's name broken. */
function infoHeight(text: number, broken: boolean): number {
    return (broken ? STATUS_BROKEN_EMS : STATUS_EMS) * text;
}

/**
 * Where the side strips' lines start: centred on the core within the table's height, or below the counters and the round
 * info where they stand over the left strip's lane (`infoFoot`), never past the table's foot (px).
 */
function sideLinesStart({
    cy,
    height,
    infoFoot,
    reach,
}: Readonly<Record<"cy" | "height" | "infoFoot" | "reach", number>>): number {
    const centred = Math.max(0, Math.min(cy - reach / 2, height - reach));
    return Math.min(Math.max(centred, infoFoot), height - reach);
}

/** A desktop's layout at a river tile and a plan, with its own tile's share of the river tile. */
function desktopAt(
    { box, chrome, tier: tierAtRecord }: BoardFrame,
    rw: number,
    plan: DesktopPlan,
): DesktopLayout & { readonly ownShare: number } {
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
    const reserved = ownRow({ height, margin: 0, ow: wholeOwn, rw });
    const { handTop, oh, ownMeldRise, ownMeldTile } = ownRow({ height, margin: 0, ow, rw });
    const centreHeight = DESKTOP_CENTRE_TILES * rw;
    const centreWidth = RIVER_ROW_SIZE * rw;
    const drop = latestDropGap(rw);
    const decisionH = Math.max(DECISION_FLOOR, Math.floor(DECISION_BY_RIVER * rw));
    const topGap = gap + edge;
    const aboveCentre = drop + riverRows(rw, topGap);
    const core = aboveCentre + centreHeight + drop + riverRows(rw, gap);
    const coreRoomTop = rh + TILE_EDGE_SHARE * rw + TOP_HAND_GAP * rw;
    const slack = handTop - ownMeldRise - edge - coreRoomTop - core;
    const coreTop = coreRoomTop + slack;
    const cy = coreTop + aboveCentre + centreHeight / 2;
    const decisionTier = atDecisionScale(tier, decisionH);
    const reach = sideStripReach(rw);
    const place = plan.info;
    const info = desktopInfo(tier, { colLeft: column.left, place, rw });
    const linesStart = sideLinesStart({ cy, height, infoFoot: info.linesFloor, reach });
    const ownPill = handTop + oh - tier.pillH;

    const lengths = Object.fromEntries([
        ...chromeLengths(decisionTier),
        ["action-text", actionText(decisionH)],
        ["actions-band-w", timerWidth(decisionH)],
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
            { drop, gap, topGap },
        ),
    ]);
    return {
        infoInRow:
            infoHolds({ colLeft: column.left, place, rw }) &&
            (info.linesFloor === 0 || linesStart + reach <= ownPill - LINE_PLATE_GAP),
        lengths,
        ownShare: fitted / rw,
        stacked: slack >= 0 && reach <= height,
        tall:
            reserved.handTop - reserved.ownMeldRise - edge - coreRoomTop - core >= 0 &&
            reach <= height,
        wide: fitted >= OWN_BY_RIVER_LEAST * rw && column.left >= BAR_MIN,
    };
}

/**
 * The left river's longest reach under the centre's middle: its rows from the centre's top, a sideways riichi tile, the
 * latest discard's gap and a tile's edge (px).
 */
function leftRiverReach(rw: number, drop: number): number {
    return (
        -(DESKTOP_CENTRE_TILES / 2) * rw +
        ROW_BEFORE_SIDEWAYS * rw +
        rw * TILE_ASPECT +
        drop +
        TILE_EDGE_SHARE * rw
    );
}

/** The own row at an own tile: its top, its tile's height, its melds' tile and the rise two of them take over the hand. */
type OwnRow = Readonly<Record<"handTop" | "oh" | "ownMeldRise" | "ownMeldTile", number>>;

/**
 * The own row at an own tile (px): its top on the board's bottom less the tile and its edge or the `margin`, whichever
 * is deeper (a desktop keeps none, a phone its margin).
 */
function ownRow({
    height,
    margin,
    ow,
    rw,
}: Readonly<Record<"height" | "margin" | "ow" | "rw", number>>): OwnRow {
    const oh = ow * TILE_ASPECT;
    const ownMeldTile = Math.max(FACE_FLOOR, Math.min(OWN_MELD_SCALE * rw, ow));
    return {
        handTop: height - Math.max(margin, ow * TILE_EDGE_SHARE) - oh,
        oh,
        ownMeldRise: Math.max(0, 2 * ownMeldTile - oh),
        ownMeldTile,
    };
}

/**
 * A desktop tier with its decisions' sizes at its decision control's height (a control's least width and the timer's);
 * the play switches stay the tier's, so the bar holds them named and no chip goes under the control floor.
 */
function atDecisionScale(tier: TierChrome, decisionH: number): TierChrome {
    return {
        ...tier,
        actionMinW: DECISION_SQUARE * decisionH,
        timerW: timerWidth(decisionH),
    };
}

/** A phone's chrome at its river tile: the small tier's px, growing with the river tile past `PHONE_CHROME_RIVER`. */
function phoneChrome(rw: number): PhoneChrome {
    const scale = Math.max(1, rw / PHONE_CHROME_RIVER);
    const control = PHONE_CHROME.controlH * scale;
    return {
        ...PHONE_CHROME,
        controlH: control,
        doraW: PHONE_CHROME.doraW * scale,
        movesH: control,
        pillH: PHONE_CHROME.pillH * scale,
        switchH: control,
        timerW: PHONE_CHROME.timerW * scale,
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
        ["timer-w", tier.timerW],
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
    const topKans = 2 * (sideStripReach(rw) - fullReach(rw, "top") / 2 + lane);
    const columnWidth = Math.max(
        TABLE_COLUMN_TILES * rw,
        core + 2 * (lane + PLATE_GAP),
        Math.min(width - 2 * barLeast, topKans),
        beside ? FULL_HAND * ow + 2 * (lane + STEP_IN_GAP) : 0,
    );
    const left = (width - columnWidth) / 2;
    return { left, right: left + columnWidth };
}

/** A phone's panel's free box: equal gaps on a live board, a replay's clear of the right bar, which holds its moves. */
function phonePanel(slots: BoardSlots, width: number, columnRight: number): BoardEdges {
    return {
        bottom: PANEL_GAP,
        left: PANEL_GAP,
        right: slots.band === "replay" ? width - columnRight + PANEL_GAP : PANEL_GAP,
        top: PANEL_GAP,
    };
}

/**
 * The plates' rectangle: the left pair's right edges and the right pair's left edges `across` off the centre's middle,
 * each pill `width` wide at most; the top row's pills' top and the bottom row's (px); the tap box's padding; and whether
 * the rows hold a pill above the right river's reserved top and above the own row.
 */
interface PlateRect {
    readonly across: number;
    readonly bottom: number;
    readonly fits: boolean;
    readonly pad: number;
    readonly top: number;
    readonly width: number;
}

/**
 * The plates as one rectangle in the core's corners: the top seat's top-left, the right seat's top-right,
 * the left seat's bottom-left and the own one bottom-right. The columns stand a gap past the top river's run-on and the
 * centre on the left and past the bottom river's run-on and the centre on the right, mirrored about the centre's middle;
 * the rows a gap above the centre and the right river's reserved top and under the centre and the left river's reserve,
 * mirrored about it where the core's top and `rowLimit` (the own row's line end) let them, each row level otherwise.
 */
function plateRect(at: (name: string) => number, pillH: number, rowLimit: number): PlateRect {
    const rw = at("rw");
    const cx = at("cx");
    const cy = at("cy");
    const lane = sideLane(rw);
    const pad = (plateBoxHeight({ pillH }) - pillH) / 2;
    const centreTop = cy - at("h");
    const centreBottom = cy + at("h");
    const leftRiverEnd =
        cy -
        at("h") +
        ROW_BEFORE_SIDEWAYS * rw +
        at("rh") +
        at("latest-drop-gap") +
        TILE_EDGE_SHARE * rw;
    const rightRiverTop =
        cy + at("h") - ROW_BEFORE_SIDEWAYS * rw - at("rh") - at("latest-drop-gap");
    const leftLimit = Math.min(at("reach-top-left"), cx - at("hx")) - PLATE_GAP;
    const rightLimit = Math.max(at("reach-bottom-right"), cx + at("hx")) + PLATE_GAP;
    const across = Math.max(cx - leftLimit, rightLimit - cx);
    const topLimit = Math.min(centreTop, rightRiverTop) - PLATE_GAP;
    const bottomFloor = Math.max(leftRiverEnd, centreBottom) + PLATE_GAP;
    const bottomLimit = rowLimit - pad;
    const down = Math.max(cy - topLimit, bottomFloor - cy);
    const mirrored = cy - down - pillH >= at("core-top") && cy + down + pillH <= bottomLimit;
    const top = mirrored ? cy - down - pillH : Math.max(at("core-top"), topLimit - pillH);
    const bottom = mirrored ? cy + down : Math.min(bottomFloor, bottomLimit - pillH);
    return {
        across,
        bottom,
        fits:
            at("core-top") + pillH <= Math.min(centreTop, rightRiverTop - PLATE_GAP) + 0.001 &&
            bottomLimit - pillH >= Math.max(leftRiverEnd, centreBottom) - 0.001,
        pad,
        top,
        width: Math.min(
            cx - across - (at("col-left") + lane + PLATE_GAP),
            at("col-right") - lane - PLATE_GAP - (cx + across),
        ),
    };
}

function plateLengths(
    width: number,
    at: (name: string) => number,
    rect: PlateRect,
): [string, number][] {
    return [
        ["plate-bottom-top", rect.bottom - rect.pad],
        ["plate-left-right", width - (at("cx") - rect.across)],
        ["plate-right-left", at("cx") + rect.across],
        ["plate-top-top", rect.top - rect.pad],
        ["plate-w", rect.width],
    ];
}

/**
 * A phone's lengths at a river and own tile, in px; whether its places fit them: the centre at its least height, both
 * side strips' lines a full concealed hand long (three pons may reach into the top margin) from the top margin to the
 * bars' foot (above the own row, or `beside` it at the board's foot), both bars as wide as the wider one's contents need, the plates' rows holding a pill above the right river's reserved top and above the own row (`plateRect`); and whether the
 * decisions' band holds `call_prompt`'s rows and the right bar a replay's column under the cog.
 */
function phoneLayout(
    frame: BoardFrame,
    { beside, ow, rw }: { readonly beside: boolean; readonly ow: number; readonly rw: number },
): {
    readonly fits: boolean;
    readonly holdsKans: boolean;
    readonly holdsPrompt: boolean;
    readonly holdsReplay: boolean;
    readonly lengths: BoardLengths;
} {
    const { box, slots } = frame;
    const { height, width } = box;
    const chrome = phoneChrome(rw);
    const { controlH, coreGap, m, sep } = chrome;
    const rh = rw * TILE_ASPECT;
    const { handTop, oh, ownMeldRise, ownMeldTile } = ownRow({ height, margin: m, ow, rw });
    const rowTop = sideLineEnd(handTop, ownMeldRise, STRIP_CONTROL_CLEAR);
    const foot = beside ? height - m : rowTop;
    const line = foot - m;
    const coreTop = m + rh + sep;
    const gap = riverGap(rw);
    const rows = riverRows(rw, gap);
    const centreTop = coreTop + LATEST_DISCARD_GAP + rows;
    const heightRoom = handTop - coreGap - LATEST_DISCARD_GAP - rows - centreTop;
    const centreWidth = Math.max(RIVER_ROW_SIZE * rw, PHONE_CENTRE_MIN_WIDTH);
    const replayRoom = phoneControlsBottom(foot) - phoneUnderCog(m, rw);
    const replay = phoneReplayBlock(chrome, replayRoom);
    const barLeast = Math.max(
        phoneLeftBarLeast(chrome),
        phoneRightBarLeast(chrome, replay.width, rw),
    );
    const column = phoneColumn({ barLeast, beside, width }, { centreWidth, ow, rw });
    const cy = centreTop + heightRoom / 2;

    const lengths = Object.fromEntries([
        ...chromeLengths(chrome),
        ["badge-h", plateBoxHeight(chrome)],
        ...cornerLengths(rw),
        ...panelLengths(phonePanel(slots, width, column.right)),
        ["col-left", column.left],
        ["col-right", column.right],
        ["control-h", controlH],
        ["core-top", coreTop],
        ["hand-top", handTop],
        ["m", m],
        ["oh", oh],
        ["ow", ow],
        ["own-end", beside ? (width + FULL_HAND * ow) / 2 : width - m],
        ["own-meld-rise", ownMeldRise],
        ["own-meld-tile", ownMeldTile],
        ...coreLengths(
            { cx: width / 2, cy, height: heightRoom, rw, width: centreWidth },
            { drop: LATEST_DISCARD_GAP, gap, topGap: gap },
        ),
        ["side-reach", phoneSideReach(rw, line)],
        ["switches-bottom", foot],
    ]);
    function at(name: string): number {
        return lengths[name] ?? 0;
    }
    const plates = plateRect(at, chrome.pillH, rowTop);
    const band = phoneActions(at);
    const fits =
        heightRoom >= PHONE_CENTRE_MIN_HEIGHT &&
        fullReach(rw, "left") <= rowTop - m &&
        ponsReach(rw) <= foot &&
        column.left >= barLeast - 0.001 &&
        plates.fits;
    return {
        fits,
        holdsKans: tightKansReach(rw) <= line + STRIP_CONTROL_CLEAR,
        holdsPrompt:
            band.bottom - band.top >=
            phonePromptHeight(band.right - band.left, chrome.timerW) - 0.001,
        holdsReplay: replay.height <= replayRoom,
        lengths,
    };
}

/**
 * A phone's layout at a river and own tile: its side lanes at the table column's edges above the own row, or beside the
 * own row, the lanes and bars running down past it, where above it they do not fit, or do not hold `PHONE_LINE_KANS`
 * or the decisions' band `call_prompt` or the right bar a replay's column, and beside it they fit.
 */
function phoneLaid(
    frame: BoardFrame,
    tiles: Readonly<Record<"ow" | "rw", number>>,
): ReturnType<typeof phoneLayout> {
    const above = phoneLayout(frame, { ...tiles, beside: false });
    if (above.fits && above.holdsKans && above.holdsPrompt && above.holdsReplay) {
        return above;
    }
    const beside = phoneLayout(frame, { ...tiles, beside: true });
    return beside.fits || !above.fits ? beside : above;
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

/**
 * A phone's root sizes and the lengths the stylesheet reads with them, in px: the joint solve above the own tile's
 * floor (`phoneSolve`); where that leaves the river tile under the face floor (a box as short as a browser's bars leave
 * it), the solve above the tap floor instead, when it lifts the river tile; the smallest pair where none fits.
 */
function phoneLengths(frame: BoardFrame): BoardLengths {
    const solved = phoneSolveHoldingPrompt(frame, PHONE_OWN_FLOOR);
    if (solved !== null && (solved["rw"] ?? 0) >= FACE_FLOOR) {
        return solved;
    }
    const tapFloored = phoneSolveHoldingPrompt(frame, PHONE_OWN_TAP_FLOOR);
    if (tapFloored !== null && (tapFloored["rw"] ?? 0) > (solved?.["rw"] ?? 0)) {
        return tapFloored;
    }
    return (
        solved ??
        phoneLayout(frame, { beside: false, ow: PHONE_OWN_TAP_FLOOR, rw: PHONE_SMALLEST_RIVER })
            .lengths
    );
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
    readonly areas: Readonly<
        Record<ShellSlot, BoardRect> & Partial<Record<"info" | "toasts", BoardRect>>
    >;
    readonly lengths: readonly [string, number][];
    readonly strips: StripRooms;
    readonly switches: SwitchesForm;
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
 * control's least width to its height; the timer's width to its height, at least `DECISION_TIMER_LEAST` (px).
 */
const DECISION_BY_RIVER = 0.85;
const DECISION_FLOOR = 40;
const DECISION_GAP_SHARE = 1 / 8;
const DECISION_SQUARE = 4 / 3;
const DECISION_TIMER_SHARE = 1.75;
const DECISION_TIMER_LEAST = 72;

/** A desktop's notices' toasts stand this far under the left river's longest reach (px). */
const TOASTS_RIVER_GAP = 4;

/** A control's label text: this share of its height, never under the floor (px). */
const ACTION_TEXT_SHARE = 0.38;
const ACTION_TEXT_MIN = 14;

function actionText(height: number): number {
    return Math.max(ACTION_TEXT_MIN, ACTION_TEXT_SHARE * height);
}

/** The timer's width at a control's height (px). */
function timerWidth(height: number): number {
    return Math.max(DECISION_TIMER_SHARE * height, DECISION_TIMER_LEAST);
}

/**
 * A phone's decision row, the gap between its decisions and between its band's rows (px); the stylesheet's `$row`,
 * `$small-decision-gap` and `$phone-band-row-gap`.
 */
const PHONE_DECISION_ROW = 40;
const PHONE_DECISION_GAP = 6;
const PHONE_BAND_ROW_GAP = 2;

/**
 * `call_prompt`'s controls on a phone's 40px row at the widest of the three languages' labels (px): the pass (Japanese's
 * スキップ), a tiled chi, and a kan or a pon; the band lays the pass and the timer as one piece, then two tiled chis, a pon
 * and a kan.
 */
const PHONE_PASS_W = 68;
const PHONE_TILED_CHI_W = 98;
const PHONE_CALL_W = 48;

/** A phone's left bar's fields keep this far off what they stand past (px). */
const FIELD_GAP = 6;

/** A phone's play switches stand in rows of this many chips, a block short enough to leave the notices their field. */
const PHONE_SWITCH_COLUMNS = 2;

/** Where the river's rows meet the board, from the tile slice's shape. */
const ROW_BEFORE_SIDEWAYS = RIVER_ROW_SIZE - 1;

/** The height `call_prompt`'s controls take in a phone's band this wide, wrapping up in rows (px). */
function phonePromptHeight(bandWidth: number, timerW: number): number {
    const pieces = [
        PHONE_PASS_W + PHONE_DECISION_GAP + timerW,
        PHONE_TILED_CHI_W,
        PHONE_TILED_CHI_W,
        PHONE_CALL_W,
        PHONE_CALL_W,
    ];
    let rows = 1;
    let used = 0;
    for (const piece of pieces) {
        const along = used === 0 ? piece : used + PHONE_DECISION_GAP + piece;
        if (along > bandWidth && used > 0) {
            rows += 1;
            used = piece;
        } else {
            used = along;
        }
    }
    return rows * PHONE_DECISION_ROW + (rows - 1) * PHONE_BAND_ROW_GAP;
}

function phoneLeftBarLeast(chrome: PhoneChrome): number {
    const counters = countersAt(FACE_FLOOR, DORA_SLOTS).width;
    const switches = PHONE_SWITCH_COLUMNS * chrome.switchH;
    const notices = NOTICE_FIELD_EMS * NOTICE_TEXT_MIN;
    return chrome.m + Math.max(counters, switches, notices) + FIELD_GAP;
}

function phoneRightBarLeast(chrome: PhoneChrome, replayWidth: number, rw: number): number {
    const notices = NOTICE_FIELD_EMS * NOTICE_TEXT_MIN;
    return ACTIONS_GAP + Math.max(menuSize(rw), replayWidth, notices) + chrome.m;
}

/** A phone's right bar's controls' top: under the cog and a gap (px). */
function phoneUnderCog(m: number, rw: number): number {
    return m + menuSize(rw) + ACTIONS_GAP;
}

/** A phone's right bar's controls' bottom: a gap above the bars' foot, where the side strips' lines end (px). */
function phoneControlsBottom(foot: number): number {
    return foot + STRIP_CONTROL_CLEAR - ACTIONS_GAP;
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

function phoneActions(at: (name: string) => number): BoardRect {
    const rw = at("rw");
    const lane = sideLane(rw);
    const bottom = at("hand-top") - at("own-meld-rise") - PHONE_BAND_OVER_OWN_ROW;
    const leftRiverEnd =
        at("cy") - at("h") + ROW_BEFORE_SIDEWAYS * rw + at("rh") + at("latest-drop-gap");
    return {
        bottom,
        left:
            bottom - PHONE_DECISION_ROW >= leftRiverEnd
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

/** The top strip's melds keep this far above the core and the top badge (px). */
const TOP_CORE_CLEAR = 8;
const TOP_BADGE_CLEAR = 6;

/**
 * Where an opponent's side strips stand, by their family's places (px): the left line from `leftStart` down to
 * `leftEnd`, its melds kept off the own row from `lineClear` past that end down to the board's foot; the right one from
 * its origin `rightEnd` up to `rightStart`; and the top plate's box's top, which the top strip's melds keep above.
 */
interface StripPlaces {
    readonly leftStart: number;
    readonly leftEnd: number;
    readonly rightStart: number;
    readonly rightEnd: number;
    readonly lineClear: number;
    readonly ownStart: number;
    readonly topBadgeTop: number;
    readonly topEnd: number;
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
    const top = topLine(at, places.topEnd);
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
                bottom: m + STACKED_DEPTH * rw,
                left: top.start,
                right: top.anchor,
                top: m,
            },
        },
        strips: {
            gap: at("g") + MELD_GAP_EXTRA,
            left: { deepLine: leftLine, line: leftLine, obstacles: [pastLine] },
            right: { deepLine: rightLine, line: rightLine, obstacles: [] },
            rw,
            top: {
                ...top,
                badgeDepth: places.topBadgeTop - TOP_BADGE_CLEAR - TILE_EDGE_SHARE * rw - m,
                depth: at("core-top") - TOP_CORE_CLEAR - m,
                lane: 0,
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
): Readonly<Record<"anchor" | "start", number>> {
    const reach = fullReach(at("rw"), "top");
    const start = at("col-left") + sideLane(at("rw"));
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
 * A bar's contents keep this far off its edges and each other; the notices and the counters this far off the left
 * strip, the field never narrower than the notices' least for it (px).
 */
const BAR_GAP = 6;
const FIELD_STRIP_GAP = 12;
const FIELD_LEAST = 84;

/** Where a desktop's notices' field and counters end, off the left strip at the table's edge `colLeft` (px). */
function fieldRight(colLeft: number): number {
    return Math.max(colLeft - FIELD_STRIP_GAP, Math.min(colLeft - BAR_GAP, BAR_GAP + FIELD_LEAST));
}

/** The gap between a desktop replay's moves and its options, in the gaps between its controls. */
const REPLAY_GROUP_GAPS = 2;

/**
 * A desktop replay's control: this share of a river tile, never under the control floor (px); the columns its block may
 * stand in, fewest first.
 */
const REPLAY_BY_RIVER = 0.95;
const REPLAY_CONTROL_FLOOR = 40;
const REPLAY_COLUMNS = [1, 2, 3] as const;

/** The furiten mark's height in its text's ems, and its text's least size (px); `.board-furiten` mirrors both. */
const FURITEN_EMS = 1.5;
const FURITEN_TEXT_MIN = 12;

/** The play switches' form: each switch showing its name, or the letters' joined column. */
type SwitchesForm = "names" | "letters";

/** What a family places in its controls' slots: their areas, the lengths their contents read, the switches' form. */
interface ControlSlots {
    readonly areas: Readonly<
        Record<"actions" | "corner" | "field" | "field-beside" | "furiten" | "switches", BoardRect>
    >;
    readonly lengths: readonly [string, number][];
    readonly switches: SwitchesForm;
}

/** A desktop replay's controls arranged in so many columns within a bar: their side, and the block they make (px). */
function replayArrangement(
    { at, tier }: ShellRoom,
    room: Readonly<Record<"across" | "down", number>>,
    columns: number,
): Readonly<Record<"columns" | "height" | "side" | "width", number>> {
    const gap = tier.replayGap;
    const rows = Math.ceil(REPLAY_MOVES / columns) + Math.ceil(REPLAY_OPTIONS / columns);
    const gaps = (rows - 2 + REPLAY_GROUP_GAPS) * gap;
    const wanted = Math.max(REPLAY_CONTROL_FLOOR, Math.round(REPLAY_BY_RIVER * at("rw")));
    const side = Math.floor(
        Math.min(wanted, (room.across - (columns - 1) * gap) / columns, (room.down - gaps) / rows),
    );
    return {
        columns,
        height: rows * side + gaps,
        side,
        width: columns * side + (columns - 1) * gap,
    };
}

/**
 * A desktop replay's controls in the right bar: the moves over the options, each `REPLAY_BY_RIVER` of a river tile
 * (never under the control floor) where the bar holds them so large, in the fewest columns holding them at their
 * largest whose block stays in the bar's lower half, else the fewest at that size; centred across the bar and standing
 * on its foot, by the own row.
 */
function replayColumn(
    room: ShellRoom,
    bar: BoardRect,
): { readonly rect: BoardRect; readonly side: number; readonly width: number } {
    const free = { across: bar.right - bar.left, down: bar.bottom - bar.top };
    const arrangements = REPLAY_COLUMNS.map((columns) => replayArrangement(room, free, columns));
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

/** A notice's text is this share of the board's, never under this size (px); its place is at least this many ems wide. */
const NOTICE_TEXT_SHARE = 0.92;
const NOTICE_TEXT_MIN = 11;
const NOTICE_FIELD_EMS = 7.5;
const DESKTOP_NOTICE_FIELD_EMS = 9;

/**
 * A desktop's notices stand as one-line toasts whose text is the board's share, never under this size; a replay's
 * status in the left bar's field never under this one (px).
 */
const TOAST_TEXT_MIN = 14;
const STATUS_TEXT_MIN = 13;

/**
 * The round info's two lines in its text's ems, three with the round's name broken where its place is under
 * `DESKTOP_NOTICE_FIELD_EMS` wide, never under `STATUS_WRAPPED_EMS`; `.replay-status` draws them (`__round`, `__count`)
 * in no more.
 */
const STATUS_EMS = 2.5;
const STATUS_BROKEN_EMS = 3.75;
const STATUS_WRAPPED_EMS = 6;

/** A side strip's line shifted under the counters ends this far over a pill's height above the own tiles' foot (px). */
const LINE_PLATE_GAP = 2;

/** A bar's controls stand centred within this many of their widths off the table column, however wide the bar. */
const BAR_REACH_WIDTHS = 3;

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
 * A desktop's controls: in the left bar the field under the counters (`info`) a clear gap off the left strip (the
 * notices over a panel, a replay's status with them; the notices' toasts and the round info take their own text), the
 * furiten mark, and the play switches' column ending at `switchesFoot`
 * (a pill's height over the own tiles' foot), each switch named where the bar holds a named one at its label's floor; in the right bar the
 * cog at its top and a replay's controls (`replayColumn`) at its foot, both centred on the bar's part next to the
 * column, and where the cog stands (its left); live play's decisions' cluster over the own row (`desktopActions`).
 */
function desktopBars(
    room: ShellRoom,
    decisions: ReturnType<typeof desktopActions>,
    { info, switchesFoot }: { readonly info: DesktopInfo; readonly switchesFoot: number },
): ControlSlots & { readonly cogLeft: number } {
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
    const switchesLeft = (leftBar.left + leftBar.right - switchesW) / 2;
    const furitenBottom = leftBar.bottom - switchesH - FURITEN_GAP;
    const furiten = { ...leftBar, bottom: furitenBottom, top: furitenBottom - furitenHeight(tier) };
    const field = {
        ...leftBar,
        bottom: furiten.top - FURITEN_GAP,
        right: fieldRight(colLeft),
        top: info.fieldTop,
    };
    const below = { ...rightBar, top: BAR_GAP + at("menu-size") + BAR_GAP };
    const replayWidth = replayColumn(room, below).width;
    const nearRight = Math.min(rightBar.right, rightBar.left + BAR_REACH_WIDTHS * replayWidth);
    const replay = replayColumn(room, { ...below, right: nearRight });
    const actions = frame.slots.band === "replay" ? replay.rect : decisions.rect;
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
            "field-beside": field,
            furiten,
            switches: {
                ...leftBar,
                left: switchesLeft,
                right: switchesLeft + switchesW,
                top: leftBar.bottom - switchesH,
            },
        },
        cogLeft: (rightBar.left + nearRight - at("menu-size")) / 2,
        lengths: [
            ["actions-bottom", actions.bottom],
            ["actions-left", actions.left],
            ["actions-right", width - actions.right],
            ["field-beside-height", Math.max(0, field.bottom - field.top)],
            ["field-height", Math.max(0, field.bottom - field.top)],
            ["field-notice-text", noticeText(tier.text, field.right - field.left)],
            ["field-w", field.right - field.left],
            ["notice-text", Math.max(TOAST_TEXT_MIN, NOTICE_TEXT_SHARE * tier.text)],
            ["status-text", info.text],
            ["replay-b", replay.side],
            ["replay-gap", tier.replayGap],
            ["replay-group-gap", REPLAY_GROUP_GAPS * tier.replayGap],
            ["replay-w", replay.width],
            ...namedLengths,
        ],
        switches: named === null ? "letters" : "names",
    };
}

/** A phone replay's options: the hide-hands switch and the round list. */
const REPLAY_OPTIONS_ON_PHONE = 2;

function phoneReplayBlock(
    { movesH, replayGap }: Pick<TierChrome, "movesH" | "replayGap">,
    room: number,
): Readonly<Record<"height" | "width", number>> {
    function block(columns: number): Readonly<Record<"height" | "width", number>> {
        const rows =
            Math.ceil(REPLAY_MOVES_ON_PHONE / columns) +
            Math.ceil(REPLAY_OPTIONS_ON_PHONE / columns);
        return {
            height: rows * movesH + (rows - 2 + REPLAY_GROUP_GAPS) * replayGap,
            width: columns * movesH + (columns - 1) * replayGap,
        };
    }
    const one = block(1);
    return one.height <= room ? one : block(2);
}

/**
 * A phone replay's controls in the right bar: the moves over the options at the tier's control, in one column where
 * the bar's height holds it, else two, standing on the bar's foot and centred across it.
 */
function phoneReplayColumn(
    { tier }: ShellRoom,
    bar: BoardRect,
): { readonly rect: BoardRect; readonly width: number } {
    const pick = phoneReplayBlock(tier, bar.bottom - bar.top);
    const left = (bar.left + bar.right - pick.width) / 2;
    return {
        rect: { bottom: bar.bottom, left, right: left + pick.width, top: bar.bottom - pick.height },
        width: pick.width,
    };
}

/**
 * A phone's controls in the bars beside the table column. The left bar: the counters at its top, the play switches'
 * block (`PHONE_SWITCH_COLUMNS` chips a row) at its foot, and the furiten mark and the notices' field between them. The right bar: the cog at its top and a replay's
 * controls (`phoneReplayColumn`) under it, to above the own row; over a panel the notices stand there too, above a
 * replay's controls. Live play's decisions stand in a band along the own row's top (`phoneActions`), as a desktop's:
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
    const leftBarRight = at("col-left") - FIELD_GAP;
    const rightBar = {
        bottom: phoneControlsBottom(at("switches-bottom")),
        left: at("col-right") + ACTIONS_GAP,
        right: width - m,
        top: phoneUnderCog(m, at("rw")),
    };
    const replay = phoneReplayColumn(room, rightBar);
    const band = phoneActions(at);
    const actions = replaying ? replay.rect : band;
    const wanted = phoneChrome(at("rw")).doraW;
    const counters = countersAt(
        Math.min(wanted, doraFitting({ perRow: DORA_SLOTS, room: leftBarRight - m, wanted })),
        DORA_SLOTS,
    );
    const switchesBottom = at("switches-bottom");
    const blockTop = switchesBottom - (SWITCH_CHIPS / PHONE_SWITCH_COLUMNS) * tier.switchH;
    const blockRight = m + PHONE_SWITCH_COLUMNS * tier.switchH;
    const furitenBottom = blockTop - FURITEN_GAP;
    const field = {
        bottom: furitenBottom - FURITEN_H - FURITEN_GAP,
        left: m,
        right: leftBarRight,
        top: m + counters.height + FIELD_GAP,
    };
    const fieldBeside = {
        ...rightBar,
        bottom: replaying ? replay.rect.top - FIELD_GAP : rightBar.bottom,
    };
    return {
        areas: {
            actions,
            corner: { bottom: height, left: rightBar.left, right: rightBar.right, top: m },
            field,
            "field-beside": fieldBeside,
            furiten: {
                bottom: furitenBottom,
                left: m,
                right: Math.min(leftBarRight, m + FURITEN_RESERVE),
                top: furitenBottom - FURITEN_H,
            },
            switches: { bottom: switchesBottom, left: m, right: blockRight, top: blockTop },
        },
        lengths: [
            ...countersLengths(counters, { left: m, top: m }),
            ["actions-bottom", actions.bottom],
            ["actions-left", actions.left],
            ["actions-right", width - actions.right],
            ["decision-bottom", band.bottom],
            ["decision-top", band.top],
            ["field-beside-height", Math.max(0, fieldBeside.bottom - fieldBeside.top)],
            ["field-height", Math.max(0, field.bottom - field.top)],
            ["notice-text", noticeText(tier.text, field.right - field.left)],
            [
                "overlay-right-beside-notices",
                Math.max(at("overlay-right"), width - rightBar.left + NOTICES_PANEL_GAP),
            ],
            ["replay-b", tier.movesH],
            ["replay-gap", tier.replayGap],
            ["replay-group-gap", REPLAY_GROUP_GAPS * tier.replayGap],
            ["replay-w", replay.width],
        ],
        switches: "letters",
    };
}

/**
 * A plate keeps this far off the centre, a river's reserve and a side strip's lane (px).
 */
const PLATE_GAP = 6;

/** A plate's box is at least the control floor tall, its pill centred in it, so a replay's plate is a whole target (px). */
const PLATE_TAP_FLOOR = 40;

/** A plate's box: its pill, at least `PLATE_TAP_FLOOR` tall. */
function plateBoxHeight({ pillH }: Pick<TierChrome, "pillH">): number {
    return Math.max(pillH, PLATE_TAP_FLOOR);
}

/** The plates' lengths and their top row's box's top, which the top strip's melds keep above. */
interface PlatePlaces {
    readonly lengths: readonly [string, number][];
    readonly topBadgeTop: number;
}

/**
 * A desktop's dora tile is this share of the river tile where its place holds it, never under the least; the counters
 * hold five indicators a gap apart (px), in rows of the most of `DORA_ROW_SIZES` their room holds.
 */
const DORA_BY_RIVER_WANTED = 0.8;
const DORA_BY_RIVER_LEAST = 0.6;
const DORA_SLOTS = 5;
const DORA_TILE_GAP = 2;
const DORA_ROW_SIZES = [5, 3, 2] as const;

/** The counters' padding and corner, in dora tiles. */
const COUNTERS_PAD_BY_DORA = 0.2;
const COUNTERS_RADIUS_BY_DORA = 0.3;

/** The counters at a dora tile: the indicators' rows on a padded card (px). */
interface Counters {
    readonly dora: number;
    readonly height: number;
    readonly pad: number;
    readonly radius: number;
    readonly rowW: number;
    readonly width: number;
}

/** The counters at a dora tile, their indicators `perRow` to a row (px). */
function countersAt(dora: number, perRow: number): Counters {
    const rows = Math.ceil(DORA_SLOTS / perRow);
    const pad = COUNTERS_PAD_BY_DORA * dora;
    const rowW = rowWidth(perRow, dora, DORA_TILE_GAP);
    return {
        dora,
        height: 2 * pad + rows * dora * TILE_ASPECT + (rows - 1) * DORA_TILE_GAP,
        pad,
        radius: COUNTERS_RADIUS_BY_DORA * dora,
        rowW,
        width: 2 * pad + rowW,
    };
}

/** The largest whole indicator, at most `wanted`, whose counters `perRow` to a row stand `room` wide (px). */
function doraFitting({
    perRow,
    room,
    wanted,
}: Readonly<Record<"perRow" | "room" | "wanted", number>>): number {
    return Math.min(
        wanted,
        Math.floor((room - (perRow - 1) * DORA_TILE_GAP) / (perRow + 2 * COUNTERS_PAD_BY_DORA)),
    );
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
        ["dora-radius", counters.radius],
        ["dora-row-w", counters.rowW],
        ["dora-w", counters.dora],
    ];
}

/** The counters and the round info under them: the counters' lengths, the info's place and text, the field's top. */
interface DesktopInfo {
    readonly counters: readonly [string, number][];
    readonly fieldTop: number;
    readonly linesFloor: number;
    readonly rect: BoardRect;
    readonly text: number;
}

/**
 * A desktop's counters at the table's top-left corner, level with the top hand's top, and the round info (a replay's
 * round and step) under them (px). Over the left strip's lane (`place`) the counters end a plate's gap short of the
 * lane's inner edge, beside the top strip's line, in one row of five indicators `DORA_BY_RIVER_WANTED` of a river tile, smaller
 * to fit the room from the bar's edge, never under `DORA_BY_RIVER_LEAST`; in the bar they end at its edge by the left
 * strip, further left where the info under them needs the room. The info stands under them, left-aligned with them, its two lines as wide as its place (over the lane, or the
 * bar), its text fitted to `DESKTOP_NOTICE_FIELD_EMS` of them; in the bar under counters over the lane, to
 * `STATUS_WRAPPED_EMS`, the round's name broken where the place is narrower than the former; the side strips' lines start under what stands over the
 * lane (`linesFloor`). Wrapped, where none holds the row (`linesStart` where the side lines start), the counters stand
 * three and two (then two to a row) in the bar or over the lane above that start, the info in the bar.
 */
function desktopInfo(
    tier: TierChrome,
    {
        colLeft,
        linesStart = 0,
        place,
        rw,
    }: {
        readonly colLeft: number;
        readonly linesStart?: number;
        readonly place: InfoPlace;
        readonly rw: number;
    },
): DesktopInfo {
    const least = leastDora(rw);
    const wanted = Math.max(least, Math.floor(DORA_BY_RIVER_WANTED * rw));
    const barEdge = fieldRight(colLeft);
    const overLane = laneEdge(colLeft, rw);
    const rows = place === "wrap" ? DORA_ROW_SIZES : [DORA_SLOTS];
    const edgesByPlace: Readonly<Record<InfoPlace, readonly number[]>> = {
        bar: [barEdge],
        "counters-lane": [overLane],
        lane: [overLane],
        wrap: [barEdge, overLane],
    };
    const places = rows.flatMap((perRow) =>
        edgesByPlace[place].map((edge) => ({
            counters: countersAt(doraFitting({ perRow, room: edge - BAR_GAP, wanted }), perRow),
            edge,
        })),
    );
    const fallback = places.at(-2) ?? places[0];
    const { counters, edge } =
        places.find(
            (candidate) =>
                candidate.counters.dora >= least &&
                (place !== "wrap" ||
                    candidate.edge <= barEdge ||
                    candidate.counters.height + PLATE_GAP <= linesStart),
        ) ?? fallback;
    const right = place === "lane" ? overLane : barEdge;
    const breaks = place === "counters-lane";
    const infoLeast = breaks ? wrappedInfo() : leastInfo();
    const left = Math.max(BAR_GAP, Math.min(edge - counters.width, right - infoLeast));
    const top = counters.height + BAR_GAP;
    const text = Math.max(
        STATUS_TEXT_MIN,
        noticeText(tier.text, right - left, breaks ? STATUS_WRAPPED_EMS : DESKTOP_NOTICE_FIELD_EMS),
    );
    const bottom = top + infoHeight(text, right - left < DESKTOP_NOTICE_FIELD_EMS * text);
    const floors: Readonly<Record<InfoPlace, number>> = {
        bar: 0,
        "counters-lane": counters.height + PLATE_GAP,
        lane: bottom + PLATE_GAP,
        wrap: 0,
    };
    return {
        counters: countersLengths(counters, { left, top: 0 }),
        fieldTop: top,
        linesFloor: floors[place],
        rect: { bottom, left, right, top },
        text,
    };
}

/**
 * Where a desktop's counters stand, from its lengths: over the lane where the side strips' lines start below them and
 * the info, else below them alone, else in the bar where it holds their one row, else wrapped.
 */
function infoPlace({ at, tier }: ShellRoom): InfoPlace {
    const rw = at("rw");
    const colLeft = at("col-left");
    const shifted = (["lane", "counters-lane"] as const).find(
        (place) =>
            infoHolds({ colLeft, place, rw }) &&
            at("lines-start") >= desktopInfo(tier, { colLeft, place, rw }).linesFloor - 0.001,
    );
    if (shifted !== undefined) {
        return shifted;
    }
    return infoHolds({ colLeft, place: "bar", rw }) ? "bar" : "wrap";
}

/** Where a plate's box would stand with its pill's foot level with the own tiles', within the table (px). */
function rowFootPlateTop({ at, frame, tier }: ShellRoom): number {
    const pad = (plateBoxHeight(tier) - tier.pillH) / 2;
    return Math.min(
        at("hand-top") + at("oh") - tier.pillH - pad,
        frame.box.height - plateBoxHeight(tier),
    );
}

/** A desktop's plates (`plateRect`), their bottom row above the own row's melds' line end. */
function desktopPlates(room: ShellRoom): PlatePlaces {
    const { at, tier } = room;
    const rect = plateRect(
        at,
        tier.pillH,
        sideLineEnd(at("hand-top"), at("own-meld-rise"), STRIP_ROOM_GAP),
    );
    return {
        lengths: plateLengths(room.frame.box.width, room.at, rect),
        topBadgeTop: rect.top - rect.pad,
    };
}

/** A phone's plates (`plateRect`), their bottom row above the own row's line end. */
function phonePlates({ at, frame, tier }: ShellRoom): PlatePlaces {
    const rect = plateRect(
        at,
        tier.pillH,
        sideLineEnd(at("hand-top"), at("own-meld-rise"), STRIP_CONTROL_CLEAR),
    );
    return {
        lengths: plateLengths(frame.box.width, at, rect),
        topBadgeTop: rect.top - rect.pad,
    };
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
 * controls in the bars (`desktopBars`) under the counters and the round info (`desktopInfo`), the decisions in a band
 * along the own row's top (`desktopActions`), the notices in the core's bottom-left corner (`desktopToasts`), and the
 * plates in the core's corners (`desktopPlates`).
 */
function desktopShell(room: ShellRoom): BoardShell {
    const { at, tier } = room;
    const lane = sideLane(at("rw"));
    const halfRow = (FULL_HAND * at("ow")) / 2;
    const ownStart = Math.max(at("col-left") + lane, at("cx") - halfRow);
    const ownEnd = Math.min(at("col-right") - lane, at("cx") + halfRow);
    const lines = desktopSideLines(room);
    const info = desktopInfo(tier, {
        colLeft: at("col-left"),
        linesStart: lines.start,
        place: infoPlace(room),
        rw: at("rw"),
    });
    const decisions = desktopActions(room);
    const controls = desktopBars(room, decisions, {
        info,
        switchesFoot: rowFootPlateTop(room) - BAR_GAP,
    });
    const plates = desktopPlates(room);
    const strips = opponentStrips(room, {
        leftEnd: lines.end,
        leftStart: lines.start,
        lineClear: STRIP_ROOM_GAP,
        ownStart,
        rightEnd: lines.end,
        rightStart: lines.start,
        topBadgeTop: plates.topBadgeTop,
        topEnd: Math.min(topHandEnd(at), controls.cogLeft - PLATE_GAP),
    });
    const own = ownRowSlot(at, {
        end: ownEnd,
        lineEnd: sideLineEnd(at("hand-top"), at("own-meld-rise"), STRIP_ROOM_GAP),
        start: ownStart,
    });
    const toasts = desktopToasts(room);
    return {
        areas: { ...controls.areas, hand: own.area, info: info.rect, ...strips.areas, toasts },
        lengths: [
            ...controls.lengths,
            ...info.counters,
            ...plates.lengths,
            ...own.lengths,
            ["decision-bottom", decisions.rect.bottom],
            ["decision-top", decisions.rect.top],
            ["toasts-height", toasts.bottom - toasts.top],
            ["toasts-left", toasts.left],
            ["toasts-top", toasts.top],
            ["toasts-w", toasts.right - toasts.left],
        ],
        strips: strips.strips,
        switches: controls.switches,
    };
}

/**
 * A phone's slots: the plates in the core's corners (`phonePlates`); the side strips at the table column's
 * edges, their lines from the top margin to the bars' foot, the top one between their lanes; the own row centred on the
 * board, under both lanes to the board's right edge, or between them where they stand beside it; and the controls in
 * the bars and the decisions' band over the own row (`phoneControls`).
 */
function phoneShell(room: ShellRoom): BoardShell {
    const { at, frame } = room;
    const { width } = frame.box;
    const m = at("m");
    const ownStart = Math.max(m, (width - FULL_HAND * at("ow")) / 2);
    const lineEnd = at("switches-bottom");
    const plates = phonePlates(room);
    const strips = opponentStrips(room, {
        leftEnd: lineEnd,
        leftStart: m,
        lineClear: STRIP_CONTROL_CLEAR,
        ownStart,
        rightEnd: lineEnd,
        rightStart: m,
        topBadgeTop: plates.topBadgeTop,
        topEnd: topHandEnd(at),
    });
    const controls = phoneControls(room);
    const own = ownRowSlot(at, { end: at("own-end"), lineEnd, start: ownStart });
    return {
        areas: { ...controls.areas, hand: own.area, ...strips.areas },
        lengths: [...controls.lengths, ...plates.lengths, ...own.lengths],
        strips: strips.strips,
        switches: controls.switches,
    };
}

/** What every family's board reads alike: an opponent's hand's gaps and full reach, and a side strip's stacked depth. */
function stripFacts(rw: number): [string, number][] {
    return [
        ["bgap", hairline(rw)],
        ["dg", drawnGap(rw, "top")],
        ["side-dg", drawnGap(rw, "left")],
        ["full-reach", fullReach(rw, "left")],
        ["strip-depth", STACKED_DEPTH * rw],
    ];
}

/** A family's slots from its lengths. */
function boardShell(frame: BoardFrame, lengths: BoardLengths): BoardShell {
    function at(name: string): number {
        return lengths[name] ?? 0;
    }
    const grown = grownChrome(frame.tier, chromeGrowth(frame.chrome, at("rw")));
    const shell =
        frame.family === "phone"
            ? phoneShell({ at, frame, tier: phoneChrome(at("rw")) })
            : desktopShell({ at, frame, tier: atDecisionScale(grown, at("decision-h")) });
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
    const candidate = boxUnderEdges(input, gutteredEdges(input.safeInsets));
    const family = classifyFamily(candidate);
    const chrome = classifyChrome(candidate);
    const phone = family === "phone";
    const settled = phone ? boxUnderEdges(input, phoneEdges(input.safeInsets)) : candidate;
    const sized =
        Number.isFinite(settled.width) &&
        Number.isFinite(settled.height) &&
        settled.width > 0 &&
        settled.height > 0;
    const frame = {
        box: settled,
        chrome,
        family,
        slots: input.slots,
        tier: tierChrome(chrome, chromeShare(candidate)),
    };
    const sizes = sized ? familyLengths(frame) : {};
    const tableHeight = sizes["table-h"];
    const table = tableHeight === undefined ? frame : frameAtHeight(frame, tableHeight);
    const shell = sized ? boardShell(table, sizes) : null;
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
        switches: shell?.switches ?? "letters",
        tracks: Object.freeze(
            shell === null ? { columns: "", rows: "" } : shellTracks(shell.areas, table.box),
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
    SwitchesForm,
};
