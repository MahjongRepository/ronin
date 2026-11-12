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
 * third row run on to seven tiles, and the top river's third row's centre-facing edge, which no gap moves toward the
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
 * bar widened to hold it (any plan whose table leaves a bar that holds the row takes it there); the counters wrapped at
 * the least bar last.
 */
function desktopPlans(
    tier: TierChrome,
    rw: number,
): readonly (DesktopPlan & { readonly share: number })[] {
    const named = Math.max(BAR_MIN, namedSwitchesBar(tier));
    const info = infoBar(tier, rw);
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
function infoBar(tier: TierChrome, rw: number): number {
    return (
        BAR_GAP + Math.max(countersRow(tier, leastDora(rw)).width, leastInfo()) + FIELD_STRIP_GAP
    );
}

/** The round info's least width: its lines at the least text (px). */
function leastInfo(): number {
    return DESKTOP_NOTICE_FIELD_EMS * STATUS_TEXT_MIN;
}

/**
 * Whether the counters' one row at their least indicator stands where `place` puts it, and the round info's lines at
 * their least text with them, or in the bar under them.
 */
function infoHolds(
    tier: TierChrome,
    {
        colLeft,
        place,
        rw,
    }: { readonly colLeft: number; readonly place: InfoPlace; readonly rw: number },
): boolean {
    const row = countersRow(tier, leastDora(rw)).width;
    const inBar = fieldRight(colLeft) - BAR_GAP;
    const overLane = colLeft + sideLane(rw) - PLATE_GAP - BAR_GAP;
    const holds: Readonly<Record<InfoPlace, boolean>> = {
        bar: Math.max(row, leastInfo()) <= inBar,
        "counters-lane": row <= overLane && leastInfo() <= inBar,
        lane: Math.max(row, leastInfo()) <= overLane,
        wrap: false,
    };
    return holds[place];
}

/** A desktop's least dora indicator (px). */
function leastDora(rw: number): number {
    return Math.ceil(DORA_BY_RIVER * rw);
}

/** The counters' one row of five at an indicator (px). */
function countersRow(
    tier: TierChrome,
    size: number,
): Readonly<Record<"height" | "rowW" | "width", number>> {
    return doraBox(countersAt(tier, size / tier.doraW), DORA_SLOTS);
}

/** The round info's height under the counters at its text (px): its two lines. */
function infoHeight(text: number): number {
    return STATUS_EMS * text;
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
    const place = infoHolds(tier, { colLeft: column.left, place: "bar", rw }) ? "bar" : plan.info;
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
            infoHolds(tier, { colLeft: column.left, place, rw }) &&
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
        countersW: PHONE_CHROME.countersW * scale,
        doraW: PHONE_CHROME.doraW * scale,
        movesH: control,
        pillH: PHONE_CHROME.pillH * scale,
        switchH: control,
        timerW: PHONE_CHROME.timerW * scale,
    };
}

/** The counters' height: the indicator's, and the padding and rim above and below it. */
function countersHeight({ countersFrame, doraW }: TierChrome): number {
    return doraW * TILE_ASPECT + countersFrame;
}

/** A tier with its counters at a scale of their own: the indicator, its frame, padding, text and corner. */
function countersAt(tier: TierChrome, scale: number): TierChrome {
    return {
        ...tier,
        countersFrame: tier.countersFrame * scale,
        countersW: tier.countersW * scale,
        doraPadEnd: tier.doraPadEnd * scale,
        doraPadStart: tier.doraPadStart * scale,
        doraRadius: tier.doraRadius * scale,
        doraText: tier.doraText * scale,
        doraW: tier.doraW * scale,
    };
}

/** The counters' px the stylesheet draws them with. */
function counterLengths(tier: TierChrome): [string, number][] {
    return [
        ["counters-h", countersHeight(tier)],
        ["counters-w", tier.countersW],
        ["dora-pad-end", tier.doraPadEnd],
        ["dora-pad-start", tier.doraPadStart],
        ["dora-radius", tier.doraRadius],
        ["dora-text", tier.doraText],
        ["dora-w", tier.doraW],
    ];
}

/** The chrome px the stylesheet draws with, by its names. */
function chromeLengths(tier: TierChrome): [string, number][] {
    return [
        ["action-min-w", tier.actionMinW],
        ["callout-cap", tier.calloutCap],
        ["chip-gap", tier.chipGap],
        ["switch-label-w", tier.switchLabelW],
        ...counterLengths(tier),
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
 * more (a centre at its least width over a small river tile), as far as the bars keep `PHONE_BAR_MIN` wide enough that
 * the top strip's line holds four kans at the face floor beside its centred hand, and with both side lanes `beside` the
 * own row where they run down past it. Its edges (px).
 */
function phoneColumn(
    { beside, width }: { readonly beside: boolean; readonly width: number },
    { centreWidth, ow, rw }: Readonly<Record<"centreWidth" | "ow" | "rw", number>>,
): Readonly<Record<"left" | "right", number>> {
    const lane = sideLane(rw);
    const core = centreWidth + 2 * sideRiverReach(rw, riverGap(rw));
    const topKans = 2 * (sideStripReach(rw) - fullReach(rw, "top") / 2 + lane);
    const columnWidth = Math.max(
        TABLE_COLUMN_TILES * rw,
        core + 2 * (lane + PLATE_GAP),
        Math.min(width - 2 * PHONE_BAR_MIN, topKans),
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
 * bars' foot (above the own row, or `beside` it at the board's foot), both bars `PHONE_BAR_MIN` wide, the plates' rows holding a pill above the right river's reserved top and above the own row (`plateRect`); and whether the
 * right bar holds the offers' stack under the cog.
 */
function phoneLayout(
    frame: BoardFrame,
    { beside, ow, rw }: { readonly beside: boolean; readonly ow: number; readonly rw: number },
): {
    readonly fits: boolean;
    readonly holdsKans: boolean;
    readonly holdsOffers: boolean;
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
    const column = phoneColumn({ beside, width }, { centreWidth, ow, rw });
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
    const plates = plateRect((name) => lengths[name] ?? 0, chrome.pillH, rowTop);
    const offersRoom = phoneControlsBottom(foot) - phoneUnderCog(m, rw);
    const fits =
        heightRoom >= PHONE_CENTRE_MIN_HEIGHT &&
        fullReach(rw, "left") <= rowTop - m &&
        ponsReach(rw) <= foot &&
        column.left >= PHONE_BAR_MIN &&
        plates.fits;
    return {
        fits,
        holdsKans: tightKansReach(rw) <= line + STRIP_CONTROL_CLEAR,
        holdsOffers: offersRoom >= phoneOffersHeight(width - m - column.right - ACTIONS_GAP),
        lengths,
    };
}

/**
 * A phone's layout at a river and own tile: its side lanes at the table column's edges above the own row, or beside the
 * own row, the lanes and bars running down past it, where above it they do not fit, or do not hold `PHONE_LINE_KANS`
 * or the right bar the offers' stack, and beside it they fit.
 */
function phoneLaid(
    frame: BoardFrame,
    tiles: Readonly<Record<"ow" | "rw", number>>,
): ReturnType<typeof phoneLayout> {
    const above = phoneLayout(frame, { ...tiles, beside: false });
    if (above.fits && above.holdsKans && above.holdsOffers) {
        return above;
    }
    const beside = phoneLayout(frame, { ...tiles, beside: true });
    return beside.fits || !above.fits ? beside : above;
}

/**
 * A phone's lengths at the largest river tile that fits above `ownFloor`, then the largest own tile that fits with it,
 * at most as wide as lets a full hand stand within the board's width less its margins and at least 4/3 of the river
 * tile, never under the floor, which wins where both cannot hold; null where no pair fits. The own tile is the largest
 * whose right bar holds the offers' stack, else the least at that river tile: that bound never lowers the river tile.
 */
function phoneSolve(frame: BoardFrame, ownFloor: number): BoardLengths | null {
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
            if (laid.fits && (laid.holdsOffers || ow === least)) {
                return laid.lengths;
            }
        }
    }
    return null;
}

/**
 * A phone's root sizes and the lengths the stylesheet reads with them, in px: the joint solve above the own tile's
 * floor (`phoneSolve`); where that leaves the river tile under the face floor (a box as short as a browser's bars leave
 * it), the solve above the tap floor instead, when it lifts the river tile; the smallest pair where none fits.
 */
function phoneLengths(frame: BoardFrame): BoardLengths {
    const solved = phoneSolve(frame, PHONE_OWN_FLOOR);
    if (solved !== null && (solved["rw"] ?? 0) >= FACE_FLOOR) {
        return solved;
    }
    const tapFloored = phoneSolve(frame, PHONE_OWN_TAP_FLOOR);
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

/** The room a phone's offers' stack keeps clear above its top row (px). */
const OFFERS_HEADROOM = 4;

/** The decisions stand this far past the rivers' reach and the own melds' rise, a phone's under the right badge (px). */
const ACTIONS_GAP = 6;

/**
 * A desktop's decision control's height in river tiles, never under `DECISION_FLOOR` (px); its gap to its height; a
 * control's least width to its height; the timer's width to its height, at least `DECISION_TIMER_LEAST` (px).
 */
const DECISION_BY_RIVER = 0.85;
const DECISION_FLOOR = 40;
const DECISION_GAP_SHARE = 1 / 8;
const DECISION_SQUARE = 4 / 3;
const DECISION_TIMER_SHARE = 1.6;
const DECISION_TIMER_LEAST = 72;

/** A desktop's notices' toasts stand this far under the left river's longest reach (px). */
const TOASTS_RIVER_GAP = 4;

/**
 * A control's label text: this share of its height, never under the floor (px); a control's padding on each side and
 * the pass's label's room (Japanese's スキップ the widest), in that text's ems. The stylesheet draws the controls from
 * these.
 */
const ACTION_TEXT_SHARE = 0.38;
const ACTION_TEXT_MIN = 14;
const ACTION_PAD_EMS = 0.5;
const PASS_LABEL_EMS = 4;

function actionText(height: number): number {
    return Math.max(ACTION_TEXT_MIN, ACTION_TEXT_SHARE * height);
}

/** The timer's width at a control's height (px). */
function timerWidth(height: number): number {
    return Math.max(DECISION_TIMER_SHARE * height, DECISION_TIMER_LEAST);
}

/** The band at a control's height: the pass and the timer, one piece (px). */
function bandWidth(height: number): number {
    const pass = Math.max(
        DECISION_SQUARE * height,
        (2 * ACTION_PAD_EMS + PASS_LABEL_EMS) * actionText(height),
    );
    return pass + DECISION_GAP_SHARE * height + timerWidth(height);
}

/** A phone's decision row and the gap between its decisions (px); the stylesheet's `$row` and `$small-decision-gap`. */
const PHONE_DECISION_ROW = 40;
const PHONE_DECISION_GAP = 6;

/**
 * A phone's offers' stack (`call_prompt`'s: the timer, pass, pon beside kan and two tiled chis) in the rows a narrow right
 * bar stacks it in, and in the rows a bar that holds two tiled chis side by side pairs it in.
 */
const PHONE_STACKED_ROWS = 5;
const PHONE_PAIRED_ROWS = 3;

/** A phone's decisions' column: a tiled chi's control at least (px); a bar holds it with its gaps to the column and the edge. */
const DECISIONS_COLUMN = 98;
const PHONE_BAR_MIN = DECISIONS_COLUMN + ACTIONS_GAP + PHONE_CHROME.m;

/** A phone's left bar's fields keep this far off what they stand past (px). */
const FIELD_GAP = 6;

/** A phone's play switches stand in rows of this many chips, a block short enough to leave the notices their field. */
const PHONE_SWITCH_COLUMNS = 2;

/** Where the river's rows meet the board, from the tile slice's shape. */
const ROW_BEFORE_SIDEWAYS = RIVER_ROW_SIZE - 1;

/** The height of a phone's offers' stack in a right bar this wide (px). */
function phoneOffersHeight(barWidth: number): number {
    const rows =
        barWidth >= 2 * DECISIONS_COLUMN + PHONE_DECISION_GAP
            ? PHONE_PAIRED_ROWS
            : PHONE_STACKED_ROWS;
    return OFFERS_HEADROOM + rows * PHONE_DECISION_ROW + (rows - 1) * PHONE_DECISION_GAP;
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
 * A desktop's decisions' place, the core's bottom-right corner over the own row's right part: past the bottom river's
 * reserve (nineteen discards, its third row run on to seven tiles; less only where the corner is narrower than the pass
 * and the timer) to short of the right strip's lane, under the right river's first tile and over the own row's melds'
 * rise. Its controls wrap up from its bottom right and stand over any river tile a longer river lays past that reserve.
 */
function desktopActions({ at }: ShellRoom): { readonly rect: BoardRect } {
    const rw = at("rw");
    const right = at("col-right") - sideLane(rw) - ACTIONS_GAP;
    return {
        rect: {
            bottom: at("hand-top") - at("own-meld-rise") - ACTIONS_GAP,
            left: Math.min(
                at("reach-bottom-right") + ACTIONS_GAP,
                right - bandWidth(at("decision-h")),
            ),
            right,
            top: at("cy") + at("h") + TILE_EDGE_SHARE * rw + ACTIONS_GAP,
        },
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

/** The round info's two lines in its text's ems; `.replay-status` draws them (`__round`, `__count`) in no more. */
const STATUS_EMS = 2.5;

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

/**
 * A phone replay's controls in the right bar: the moves over the options at the tier's control, in one column where
 * the bar's height holds it, else two, standing on the bar's foot and centred across it.
 */
function phoneReplayColumn(
    { tier }: ShellRoom,
    bar: BoardRect,
): { readonly rect: BoardRect; readonly width: number } {
    const side = tier.movesH;
    const gap = tier.replayGap;
    function block(columns: number): Readonly<Record<"height" | "width", number>> {
        const rows =
            Math.ceil(REPLAY_MOVES_ON_PHONE / columns) +
            Math.ceil(REPLAY_OPTIONS_ON_PHONE / columns);
        return {
            height: rows * side + (rows - 2 + REPLAY_GROUP_GAPS) * gap,
            width: columns * side + (columns - 1) * gap,
        };
    }
    const one = block(1);
    const pick = one.height <= bar.bottom - bar.top ? one : block(2);
    const left = (bar.left + bar.right - pick.width) / 2;
    return {
        rect: { bottom: bar.bottom, left, right: left + pick.width, top: bar.bottom - pick.height },
        width: pick.width,
    };
}

/**
 * A phone's controls in the bars beside the table column. The left bar: the counters at its top, the play switches'
 * block (`PHONE_SWITCH_COLUMNS` chips a row) at its foot, and the furiten mark and the notices' field between them. The right bar: the cog at its top and under it, to above the own row, live
 * play's decisions or a replay's controls (`phoneReplayColumn`); over a panel the notices stand there too, above a
 * replay's controls.
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
    const actions = replaying ? replay.rect : rightBar;
    const counters = countersAt(tier, Math.min(1, (leftBarRight - m) / tier.countersW));
    const switchesBottom = at("switches-bottom");
    const blockTop = switchesBottom - (SWITCH_CHIPS / PHONE_SWITCH_COLUMNS) * tier.switchH;
    const blockRight = m + PHONE_SWITCH_COLUMNS * tier.switchH;
    const furitenBottom = blockTop - FURITEN_GAP;
    const field = {
        bottom: furitenBottom - FURITEN_H - FURITEN_GAP,
        left: m,
        right: leftBarRight,
        top: m + countersHeight(counters) + FIELD_GAP,
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
            ...counterLengths(counters),
            ["counters-top", m],
            ["counters-x", m],
            ["actions-bottom", actions.bottom],
            ["actions-left", actions.left],
            ["actions-right", width - actions.right],
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
 * A desktop's dora tile is at least this share of the river tile; the counters hold five indicators a gap apart inside
 * a rim (px), in rows of the most of `DORA_ROW_SIZES` their room holds.
 */
const DORA_BY_RIVER = 0.55;
const DORA_SLOTS = 5;
const DORA_TILE_GAP = 2;
const DORA_RIM = 2;
const DORA_ROW_SIZES = [5, 3, 2] as const;

/** The counters' box, their indicators `perRow` to a row (px). */
function doraBox(
    tier: TierChrome,
    perRow: number,
): Readonly<Record<"height" | "rowW" | "width", number>> {
    const rows = Math.ceil(DORA_SLOTS / perRow);
    const rowW = perRow * tier.doraW + (perRow - 1) * DORA_TILE_GAP;
    return {
        height: rows * tier.doraW * TILE_ASPECT + (rows - 1) * DORA_TILE_GAP + tier.countersFrame,
        rowW,
        width: tier.doraPadStart + rowW + tier.doraPadEnd + DORA_RIM,
    };
}

/** The largest whole indicator, at most `wanted`, whose counters `perRow` to a row stand `room` wide (px). */
function doraFitting(
    tier: TierChrome,
    { perRow, room, wanted }: Readonly<Record<"perRow" | "room" | "wanted", number>>,
): number {
    const pads = (tier.doraPadStart + tier.doraPadEnd) / tier.doraW;
    return Math.min(
        wanted,
        Math.floor((room - (perRow - 1) * DORA_TILE_GAP - DORA_RIM) / (pads + perRow)),
    );
}

/** The counters' lengths the stylesheet draws them with at a scale and in a box (px). */
function countersLengths(
    scaled: TierChrome,
    box: Readonly<Record<"height" | "rowW" | "width", number>>,
): [string, number][] {
    return [
        ...counterLengths(scaled),
        ["counters-h", box.height],
        ["counters-w", box.width],
        ["counters-top", BAR_GAP],
        ["counters-x", BAR_GAP],
        ["dora-row-w", box.rowW],
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
 * A desktop's counters at the left bar's top, left-aligned with the field under them, and the round info (a replay's
 * round and step) under them (px). In the bar or over the left strip's lane (`place`), the counters stand in one row of
 * five, each indicator the tier's size in the bar and the least over the lane, never under `DORA_BY_RIVER` of a river
 * tile; the info its two lines as wide as its place (the bar, or the counters' over the lane), its text fitted to
 * `DESKTOP_NOTICE_FIELD_EMS` of them; the side strips' lines start under what stands over the lane (`linesFloor`).
 * Wrapped, where none holds the row (`linesStart` where the side lines start), the counters stand three and two (then
 * two to a row) in the bar or over the lane above that start, the info in the bar.
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
    const onLane = place === "lane" || place === "counters-lane";
    const wanted = onLane ? least : Math.max(least, tier.doraW);
    const inBar = fieldRight(colLeft) - BAR_GAP;
    const overLane = colLeft + sideLane(rw) - PLATE_GAP - BAR_GAP;
    const rows = place === "wrap" ? DORA_ROW_SIZES : [DORA_SLOTS];
    const roomsByPlace: Readonly<Record<InfoPlace, readonly number[]>> = {
        bar: [inBar],
        "counters-lane": [overLane],
        lane: [overLane],
        wrap: [inBar, overLane],
    };
    const rooms = roomsByPlace[place];
    const places = rows.flatMap((perRow) =>
        rooms.map((room) => {
            const size = doraFitting(tier, { perRow, room, wanted });
            const scaled = countersAt(tier, size / tier.doraW);
            return { box: doraBox(scaled, perRow), overLane: room > inBar, scaled, size };
        }),
    );
    const fallback = places.at(-2) ?? places[0];
    const { box, scaled } =
        places.find(
            (candidate) =>
                candidate.size >= least &&
                (place !== "wrap" ||
                    !candidate.overLane ||
                    BAR_GAP + candidate.box.height + PLATE_GAP <= linesStart),
        ) ?? fallback;
    const top = 2 * BAR_GAP + box.height;
    const right = place === "lane" ? overLane + BAR_GAP : fieldRight(colLeft);
    const text = Math.max(
        STATUS_TEXT_MIN,
        noticeText(tier.text, right - BAR_GAP, DESKTOP_NOTICE_FIELD_EMS),
    );
    const bottom = top + infoHeight(text);
    const floors: Readonly<Record<InfoPlace, number>> = {
        bar: 0,
        "counters-lane": top - BAR_GAP + PLATE_GAP,
        lane: bottom + PLATE_GAP,
        wrap: 0,
    };
    return {
        counters: countersLengths(scaled, box),
        fieldTop: top,
        linesFloor: floors[place],
        rect: { bottom, left: BAR_GAP, right, top },
        text,
    };
}

/**
 * Where a desktop's counters stand, from its lengths: in the bar where it holds their one row, else over the lane where
 * the side strips' lines start below them and the info, else below them alone, else wrapped.
 */
function infoPlace({ at, tier }: ShellRoom): InfoPlace {
    const rw = at("rw");
    const colLeft = at("col-left");
    if (infoHolds(tier, { colLeft, place: "bar", rw })) {
        return "bar";
    }
    const shifted = (["lane", "counters-lane"] as const).find(
        (place) =>
            infoHolds(tier, { colLeft, place, rw }) &&
            at("lines-start") >= desktopInfo(tier, { colLeft, place, rw }).linesFloor - 0.001,
    );
    return shifted ?? "wrap";
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
 * controls in the bars (`desktopBars`) under the counters and the round info (`desktopInfo`), the decisions in the
 * core's bottom-right corner (`desktopActions`), the notices in its bottom-left one (`desktopToasts`), and the plates
 * in the core's corners (`desktopPlates`).
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
 * the bars (`phoneControls`).
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
