import {
    FACE_FLOOR,
    LYING_Y_SHARE,
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
 * The top strip's room (px): its anchor (where its hand ends, its area's right edge), its line's start, and the depth
 * its melds have above what they keep clear of, closer where they reach the top badge's lane.
 */
interface TopStripRoom {
    readonly anchor: number;
    readonly start: number;
    /** How far in from its start the line's melds must end, clear of what stands in under its end (px). */
    readonly inset?: number;
    readonly depth: number;
    readonly badgeDepth: number;
    readonly lane: number;
}

/** What the viewport leaves the opponents' strips: their rooms, the river tile and the gap between melds (px). */
interface StripRooms {
    readonly rw: number;
    readonly floor?: number;
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

/** A strip laid out: its melds' places, its depth as drawn and where its hand starts along its line (px). */
interface StripLayout {
    readonly melds: readonly MeldPlace[];
    readonly depth: number;
    readonly hand: number;
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

/** A hand's length along its line (px): its tiles edge to edge and a drawn tile's gap. */
function handLength({ drawn, rw, seat, tiles }: HandLine): number {
    return tiles * rw + (drawn ? drawnGap(rw, seat) : 0);
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
            end -
            sum(remaining.map((shape) => shape.units)) * LYING_Y_SHARE * tile -
            (remaining.length - 1) * gap;
        return {
            along,
            depth: meld.depth * tile,
            end: along + meld.units * LYING_Y_SHARE * tile,
            rise: 0,
            tile,
        };
    });
}

function fitSideMelds(
    shapes: readonly MeldShape[],
    room: SideStripRoom,
    fit: SideFit,
): Omit<StripLayout, "hand"> | null {
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

function getTileCandidates(rw: number, floor: number): readonly number[] {
    const largest = Math.max(floor, rw);
    return Array.from({ length: Math.ceil(largest - floor) + 1 }, (_value, step) =>
        Math.max(floor, largest - step),
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
 * melds shrink under the floor, all together, to end on the line beside the hand: a rare dense seat on a short box
 * takes smaller meld faces, never a smaller river tile and never a meld past its line over the own row or the board's
 * edge.
 */
function shrunkSideMelds(
    shapes: readonly MeldShape[],
    room: SideStripRoom,
    { gap, handEnd, rw }: Omit<SideFit, "tile">,
): Omit<StripLayout, "hand"> {
    const line = Math.min(room.line, room.deepLine);
    const units = sum(shapes.map((shape) => shape.units));
    const tile = Math.max(0, (line - handEnd - shapes.length * gap) / (units * LYING_Y_SHARE));
    const melds = placeSideMelds(shapes, { gap, tile }, line);
    return {
        depth: Math.max(UPRIGHT_DEPTH * rw, ...melds.map((meld) => meld.depth)),
        melds,
    };
}

/**
 * A side hand starts where a full hand stands centred on its line, the same place call after call, nearer the line's
 * start only as far as its melds, laid at the line's end, leave it short (px).
 */
function sideHandStart(
    seat: "left" | "right",
    content: StripContent,
    { line, melds, rooms }: { line: number; melds: readonly MeldPlace[]; rooms: StripRooms },
): number {
    const { gap, rw } = rooms;
    const centred = (line - handLength({ drawn: true, rw, seat, tiles: FULL_HAND_TILES })) / 2;
    const meldsStart = Math.min(Infinity, ...melds.map((meld) => meld.along));
    const room = meldsStart - gap - reservedHandLength(content, rw, seat);
    return Math.max(0, Math.min(centred, room));
}

/** Side melds form one line toward their owner's right, oldest at the end, at one fitting size; the hand centred. */
function sideLayout(seat: "left" | "right", content: StripContent, rooms: StripRooms): StripLayout {
    const laid = sideMeldsLayout(seat, content, rooms);
    const hand = sideHandStart(seat, content, { line: rooms[seat].line, melds: laid.melds, rooms });
    return { ...laid, hand };
}

function sideMeldsLayout(
    seat: "left" | "right",
    content: StripContent,
    rooms: StripRooms,
): Omit<StripLayout, "hand"> {
    const { rw } = rooms;
    if (content.melds.length === 0) {
        return { depth: UPRIGHT_DEPTH * rw, melds: [] };
    }
    const handEnd = reservedHandLength(content, rw, seat);
    const faceFloor = rooms.floor ?? FACE_FLOOR;
    for (const tile of getTileCandidates(rw, faceFloor)) {
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
    const floor = { handEnd, rw, tile: faceFloor };
    for (const gap of getTighterGaps(rooms.gap)) {
        const layout = fitSideMelds(content.melds, rooms[seat], { ...floor, gap });
        if (layout) {
            return layout;
        }
    }
    return shrunkSideMelds(content.melds, rooms[seat], {
        gap: Math.min(rooms.gap, MELD_GAP_TIGHT),
        handEnd,
        rw,
    });
}

/**
 * The top strip's melds' tile and gap on a line `room` long: the largest tile that fits beside the hand, kept clear of
 * what it must be, never under the face floor. Where the floor does not fit beside the hand at the room's gap, the
 * melds close their gaps at the floor, else shrink under it at the tightest gap, as a side strip's do.
 */
function topMeldLine(content: StripContent, rooms: StripRooms, room: number): MeldLine {
    const { gap, rw, top } = rooms;
    const floor = rooms.floor ?? FACE_FLOOR;
    const units = content.melds.map((meld) => meld.units);
    const count = units.length;
    const heldLen = handLength({
        drawn: false,
        rw,
        seat: "top",
        tiles: content.hand - (content.drawn ? 1 : 0),
    });
    function near(index: number): number {
        return Math.max(heldLen + gap, room - sum(units.slice(index)) * rw - (count - index) * gap);
    }
    const bounds = content.melds.map(
        (meld, index) =>
            Math.min(top.depth, top.lane - near(index) > 0 ? top.badgeDepth : Infinity) /
            (meld.depth * LYING_Y_SHARE),
    );
    const handLen = reservedHandLength(content, rw, "top");
    function fit(lineGap: number): number {
        return (room - handLen - count * lineGap) / Math.max(sum(units), 1);
    }
    if (fit(gap) >= floor) {
        return { gap, tile: Math.max(floor, Math.min(rw, fit(gap), ...bounds)) };
    }
    const closed = getTighterGaps(gap).find((tighter) => fit(tighter) >= floor);
    if (closed !== undefined) {
        return { gap: closed, tile: floor };
    }
    const tightest = Math.min(gap, MELD_GAP_TIGHT);
    return { gap: tightest, tile: Math.max(0, fit(tightest)) };
}

/**
 * The top strip: one line, its melds ending at its anchor at one size, the largest that keeps each above what it keeps
 * clear of where it stands (the top badge only for a meld reaching its lane) and fits them beside the hand, under the
 * face floor only where its tightest gaps cannot hold the floor there. Where the line's inset moves its melds in, they
 * keep the whole line's size and slide while a drawn tile still fits beside the hand, else they take the inset line's.
 */
function topLayout(content: StripContent, rooms: StripRooms): StripLayout {
    const { rw, top } = rooms;
    const units = content.melds.map((meld) => meld.units);
    const count = units.length;
    const room = top.anchor - top.start;
    const slid = room - (top.inset ?? 0);
    const handLen = reservedHandLength(content, rw, "top");
    const drawnHand = handLength({
        drawn: true,
        rw,
        seat: "top",
        tiles: content.hand - (content.drawn ? 1 : 0) + 1,
    });
    const whole = topMeldLine(content, rooms, room);
    const kept =
        slid - sum(units) * whole.tile - Math.max(0, count - 1) * whole.gap >=
        drawnHand + whole.gap;
    const { gap, tile } = kept ? whole : topMeldLine(content, rooms, slid);
    const end = handLen + Math.max(gap, slid - handLen);
    const melds = units.map((_unit, index) => ({
        along: end - (sum(units.slice(index)) * tile + (count - 1 - index) * gap),
        rise: 0,
        tile,
    }));
    return { depth: 0, hand: 0, melds };
}

function stripLayout(seat: StripSeat, content: StripContent, rooms: StripRooms): StripLayout {
    return seat === "top" ? topLayout(content, rooms) : sideLayout(seat, content, rooms);
}

/** A strip's layout as lengths (px): its melds and a side strip's depth as drawn. */
function seatLengths(seat: StripSeat, { depth, hand, melds }: StripLayout): [string, number][] {
    const places = melds.flatMap(({ along, rise, tile }, index): [string, number][] => [
        [`${seat}-meld-${index}-along`, along],
        [`${seat}-meld-${index}-tile`, tile],
        [`${seat}-meld-${index}-rise`, rise],
    ]);
    const frame: Record<StripSeat, [string, number][]> = {
        left: [
            ["left-depth", depth],
            ["left-hand-along", hand],
        ],
        right: [
            ["right-depth", depth],
            ["right-hand-along", hand],
        ],
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

export { drawnGap, handLength, ownMeldTile, stripLayout, stripLengths };
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
