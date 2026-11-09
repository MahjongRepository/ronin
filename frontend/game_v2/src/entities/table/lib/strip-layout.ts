import {
    FACE_FLOOR,
    MELD_GAP_EXTRA,
    MELD_GAP_TIGHT,
    OPPONENT_DRAWN_GAP,
    OWN_DRAWN_GAP,
    SIDE_DRAWN_GAP,
    TILE_UNITS,
    UPRIGHT_DEPTH,
} from "./board-constants";

/** An opponent's strip seat: the own row is the hand's slot, its melds scaled by their container. */
type StripSeat = "left" | "top" | "right";

/** A laid meld's length and depth from its seat's edge, in its tiles' widths. */
interface MeldShape {
    readonly units: number;
    readonly depth: number;
}

/** What a strip holds: its hand's tiles (a drawn one counted, and apart) and its melds, newest first. */
interface StripContent {
    readonly hand: number;
    readonly drawn: boolean;
    readonly melds: readonly MeldShape[];
}

/** A reserved control or hand in strip coordinates, extending inward from `depth`. */
interface StripObstacle {
    readonly from: number;
    readonly to: number;
    readonly depth: number;
}

/** A side strip's length limits and the nearby controls its melds must clear. */
interface SideStripRoom {
    readonly line: number;
    readonly deepLine: number;
    readonly obstacles: readonly StripObstacle[];
}

/**
 * The top strip's room (px): its anchor (`top-strip-x`), its line's start, and the depth its melds have above what they keep clear of, closer where
 * they reach the top badge's lane.
 */
interface TopStripRoom {
    readonly anchor: number;
    readonly start: number;
    readonly depth: number;
    readonly badgeDepth: number;
    readonly lane: number;
}

/** What the viewport leaves the opponents' strips: their rooms, the river tile and the gap between melds (px). */
interface StripRooms {
    readonly rw: number;
    readonly gap: number;
    readonly left: SideStripRoom;
    readonly right: SideStripRoom;
    readonly top: TopStripRoom;
}

/** A meld's place in its strip's frame (px): along the line, its tile's width and its rise toward the table. */
interface MeldPlace {
    readonly along: number;
    readonly tile: number;
    readonly rise: number;
}

/** A strip laid out: its melds' places, its depth as drawn and how far its frame stands short of its area's corner. */
interface StripLayout {
    readonly melds: readonly MeldPlace[];
    readonly depth: number;
}

/** A meld deeper than this many river-tile widths takes its side strip's stacked room. */
const SHALLOW_DEPTH = 1.5;
const LAYOUT_EPSILON = 0.001;

interface LaidMeld extends MeldPlace {
    readonly end: number;
    readonly depth: number;
}

function sum(values: readonly number[]): number {
    return values.reduce((total, value) => total + value, 0);
}

/** An opponent's hairline between tiles, a whole pixel (a side strip's quarter turn blurs a fractional one away). */
function hairline(rw: number): number {
    return Math.ceil(rw / TILE_UNITS);
}

/** An opponent's drawn tile's gap, a whole pixel; a side strip's is deeper by the tile edge it shows. */
function drawnGap(rw: number, seat: StripSeat): number {
    return Math.round((seat === "top" ? OPPONENT_DRAWN_GAP : SIDE_DRAWN_GAP) * rw);
}

/** A hand on its seat's line: its tiles, a drawn one counted, at the river tile's width (px). */
interface HandLine {
    readonly tiles: number;
    readonly drawn: boolean;
    readonly rw: number;
    readonly seat: StripSeat;
}

/** A hand's length along its line (px): its tiles, whole-pixel hairlines between them and a drawn tile's gap. */
function handLength({ drawn, rw, seat, tiles }: HandLine): number {
    return tiles * rw + Math.max(0, tiles - 1) * hairline(rw) + (drawn ? drawnGap(rw, seat) : 0);
}

/** A full hand's tiles, a drawn one counted, and the tiles each meld takes from it. */
const FULL_HAND_TILES = 14;
const TILES_PER_MELD = 3;

/** The hand a strip's melds fit beside: its fullest, with a drawn tile and its gap, so a draw never resizes them (px). */
function reservedHandLength(content: StripContent, rw: number, seat: StripSeat): number {
    const tiles = Math.max(content.hand, FULL_HAND_TILES - TILES_PER_MELD * content.melds.length);
    return handLength({ drawn: true, rw, seat, tiles });
}

interface MeldLine {
    readonly tile: number;
    readonly gap: number;
}

interface SideFit extends MeldLine {
    readonly rw: number;
    readonly handEnd: number;
}

function placeSideMelds(
    shapes: readonly MeldShape[],
    { tile, gap }: MeldLine,
    end: number,
): readonly LaidMeld[] {
    return shapes.map((meld, index) => {
        const remaining = shapes.slice(index);
        const along =
            end - sum(remaining.map((shape) => shape.units)) * tile - (remaining.length - 1) * gap;
        return {
            along,
            depth: meld.depth * tile,
            end: along + meld.units * tile,
            rise: 0,
            tile,
        };
    });
}

function fitSideMelds(
    shapes: readonly MeldShape[],
    room: SideStripRoom,
    fit: SideFit,
): StripLayout | null {
    const { handEnd, gap, rw } = fit;
    const offsets = placeSideMelds(shapes, fit, 0);
    const endLimits = offsets.map((meld) => {
        const limit = meld.depth < SHALLOW_DEPTH * rw ? room.line : room.deepLine;
        return limit - meld.end;
    });
    let end = Math.min(...endLimits);
    const minimumEnd = Math.max(...offsets.map((meld) => handEnd + gap - meld.along));
    while (end + LAYOUT_EPSILON >= minimumEnd) {
        const melds = placeSideMelds(shapes, fit, end);
        let shift = 0;
        for (const meld of melds) {
            for (const obstacle of room.obstacles) {
                if (
                    meld.depth > obstacle.depth + LAYOUT_EPSILON &&
                    meld.along < obstacle.to - LAYOUT_EPSILON &&
                    meld.end > obstacle.from + LAYOUT_EPSILON
                ) {
                    shift = Math.max(shift, meld.end - obstacle.from);
                }
            }
        }
        if (shift === 0) {
            return {
                depth: Math.max(UPRIGHT_DEPTH * rw, ...melds.map((meld) => meld.depth)),
                melds,
            };
        }
        end -= shift;
    }
    return null;
}

function getTileCandidates(rw: number): readonly number[] {
    const largest = Math.max(FACE_FLOOR, rw);
    return Array.from({ length: Math.ceil(largest - FACE_FLOOR) + 1 }, (_value, step) =>
        Math.max(FACE_FLOOR, largest - step),
    );
}

/** The narrower gaps to try, widest first, once the face floor does not fit the line at the room's gap (px). */
function getTighterGaps(gap: number): readonly number[] {
    return Array.from({ length: Math.max(0, Math.ceil(gap - MELD_GAP_TIGHT)) }, (_value, step) =>
        Math.max(MELD_GAP_TIGHT, gap - step - 1),
    );
}

/**
 * Where even the face floor at the tightest gap does not fit the line (a phone box too short to reserve four kans), the
 * melds lie at the floor from the hand on at that gap, moved along past every obstacle a deeper one would meet (the
 * badge, the switches, the own row), past the line if need be: the accepted overflow of a rare dense seat on a short
 * phone, never a smaller river tile for it and never a meld over a control.
 */
function overflowSideMelds(
    shapes: readonly MeldShape[],
    room: SideStripRoom,
    fit: SideFit,
): StripLayout {
    const { handEnd, gap, rw } = fit;
    const offsets = placeSideMelds(shapes, fit, 0);
    let end = Math.max(...offsets.map((meld) => handEnd + gap - meld.along));
    for (let step = 0; step <= room.obstacles.length; step += 1) {
        const melds = placeSideMelds(shapes, fit, end);
        let shift = 0;
        for (const meld of melds) {
            for (const obstacle of room.obstacles) {
                if (
                    meld.depth > obstacle.depth + LAYOUT_EPSILON &&
                    meld.along < obstacle.to - LAYOUT_EPSILON &&
                    meld.end > obstacle.from + LAYOUT_EPSILON
                ) {
                    shift = Math.max(shift, obstacle.to - meld.along);
                }
            }
        }
        if (shift === 0) {
            return {
                depth: Math.max(UPRIGHT_DEPTH * rw, ...melds.map((meld) => meld.depth)),
                melds,
            };
        }
        end += shift;
    }
    const melds = placeSideMelds(shapes, fit, end);
    return {
        depth: Math.max(UPRIGHT_DEPTH * rw, ...melds.map((meld) => meld.depth)),
        melds,
    };
}

/** Side melds form one line toward their owner's right, oldest at the end, at one fitting size. */
function sideLayout(seat: "left" | "right", content: StripContent, rooms: StripRooms): StripLayout {
    const { rw } = rooms;
    if (content.melds.length === 0) {
        return { depth: UPRIGHT_DEPTH * rw, melds: [] };
    }
    const handEnd = reservedHandLength(content, rw, seat);
    for (const tile of getTileCandidates(rw)) {
        const layout = fitSideMelds(content.melds, rooms[seat], {
            gap: rooms.gap,
            handEnd,
            rw,
            tile,
        });
        if (layout) {
            return layout;
        }
    }
    const floor = { handEnd, rw, tile: FACE_FLOOR };
    for (const gap of getTighterGaps(rooms.gap)) {
        const layout = fitSideMelds(content.melds, rooms[seat], { ...floor, gap });
        if (layout) {
            return layout;
        }
    }
    return overflowSideMelds(content.melds, rooms[seat], {
        ...floor,
        gap: Math.min(rooms.gap, MELD_GAP_TIGHT),
    });
}

/**
 * The top strip: one line, its melds ending at its anchor at one size, the largest that keeps each above what it keeps
 * clear of where it stands (the top badge only for a meld reaching its lane) and fits them beside the hand, never under
 * the face floor.
 */
function topLayout(content: StripContent, { gap, rw, top }: StripRooms): StripLayout {
    const { anchor, badgeDepth, depth, lane, start } = top;
    const units = content.melds.map((meld) => meld.units);
    const count = units.length;
    const total = sum(units);
    const handLen = reservedHandLength(content, rw, "top");
    const heldLen = handLength({
        drawn: false,
        rw,
        seat: "top",
        tiles: content.hand - (content.drawn ? 1 : 0),
    });
    const room = anchor - start;
    function near(index: number): number {
        return Math.max(heldLen + gap, room - sum(units.slice(index)) * rw - (count - index) * gap);
    }
    const bounds = content.melds.map(
        (meld, index) =>
            Math.min(depth, lane - near(index) > 0 ? badgeDepth : Infinity) / meld.depth,
    );
    const fit = (room - handLen - count * gap) / Math.max(total, 1);
    const tile = Math.max(FACE_FLOOR, Math.min(rw, fit, ...bounds));
    const end = handLen + Math.max(gap, room - handLen);
    const melds = units.map((_unit, index) => ({
        along: end - (sum(units.slice(index)) * tile + (count - 1 - index) * gap),
        rise: 0,
        tile,
    }));
    return { depth: 0, melds };
}

function stripLayout(seat: StripSeat, content: StripContent, rooms: StripRooms): StripLayout {
    return seat === "top" ? topLayout(content, rooms) : sideLayout(seat, content, rooms);
}

/** A strip's layout as lengths (px): its melds and a side strip's depth as drawn. */
function seatLengths(seat: StripSeat, { depth, melds }: StripLayout): [string, number][] {
    const places = melds.flatMap(({ along, rise, tile }, index): [string, number][] => [
        [`${seat}-meld-${index}-along`, along],
        [`${seat}-meld-${index}-tile`, tile],
        [`${seat}-meld-${index}-rise`, rise],
    ]);
    const frame: Record<StripSeat, [string, number][]> = {
        left: [["left-depth", depth]],
        right: [["right-depth", depth]],
        top: [],
    };
    return [...frame[seat], ...places];
}

/** The strips' layouts as the lengths their stylesheet places them from, by seat (px). */
function stripLengths(
    rooms: StripRooms,
    contents: Readonly<Record<StripSeat, StripContent>>,
): Readonly<Record<string, number>> {
    return Object.fromEntries(
        (["left", "top", "right"] as const).flatMap((seat) =>
            seatLengths(seat, stripLayout(seat, contents[seat], rooms)),
        ),
    );
}

/** What the own melds keep before the row's end for rounding (px). */
const OWN_MELDS_SLACK = 2;

/**
 * The own row from the hand's start (px): its width to the board's edge, its hand's tile and river gap, and its melds'
 * largest tile.
 */
interface OwnRow {
    readonly width: number;
    readonly ow: number;
    readonly gap: number;
    readonly cap: number;
}

/**
 * The own melds' one tile from their structure alone: their cap where they fit beside the hand at its fullest with its
 * drawn tile and gap, never under the face floor; so a draw, a discard or anything but a call never resizes them.
 */
function ownMeldTile(row: OwnRow, melds: readonly MeldShape[]): number {
    const { cap, gap, ow, width } = row;
    const units = sum(melds.map((meld) => meld.units));
    if (units === 0) {
        return cap;
    }
    const tiles = FULL_HAND_TILES - TILES_PER_MELD * melds.length;
    const hand = tiles * ow + (tiles - 1) * (ow / TILE_UNITS) + 2 * OWN_DRAWN_GAP * ow;
    const gaps = (melds.length - 1) * (gap + MELD_GAP_EXTRA) + OWN_MELDS_SLACK;
    const room = width - hand - gaps;
    return Math.max(FACE_FLOOR, Math.min(cap, room / units));
}

export { drawnGap, hairline, handLength, ownMeldTile, stripLayout, stripLengths };
export type {
    MeldShape,
    MeldPlace,
    SideStripRoom,
    StripContent,
    StripLayout,
    StripRooms,
    StripSeat,
    StripObstacle,
    TopStripRoom,
};
