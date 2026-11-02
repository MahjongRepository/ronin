import {
    FACE_FLOOR,
    OPPONENT_DRAWN_GAP,
    STRIP_LINES_GAP,
    TILE_ASPECT,
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

/**
 * A side strip's room along its line from its anchor (px): its first line's for a meld a tile's height deep and for a
 * stacked one (the left strip's shallower meld runs on past the switches, which step in past its depth); its second
 * line's; and where that line starts (right) or ends (left).
 */
interface SideStripRoom {
    readonly line: number;
    readonly deepLine: number;
    readonly secondLine: number;
    readonly secondAt: number;
}

/**
 * The top strip's room (px): its anchor (`top-strip-x`), the farthest a dense strip may move it (upright, to the
 * board's edge) or none, its line's start, and the depth its melds have above what they keep clear of, closer where
 * they reach the top badge's lane.
 */
interface TopStripRoom {
    readonly anchor: number;
    readonly cap: number | null;
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
    readonly pull: number;
}

/**
 * Each seat's placement: a side strip's melds wrap to a second line, which runs from the band's start up (right) or
 * ends at its room's end (left); the top strip's (and the own row's) melds keep one line and scale.
 */
const STRIP_POLICY = {
    left: { melds: "wrap", second: "end" },
    right: { melds: "wrap", second: "start" },
    top: { melds: "scale" },
} as const;

/** A meld deeper than this, in its tiles' widths, takes its side strip's stacked room. */
const SHALLOW_DEPTH = 1.5;

function sum(values: readonly number[]): number {
    return values.reduce((total, value) => total + value, 0);
}

/** An opponent's hairline between tiles, a whole pixel (a side strip's quarter turn blurs a fractional one away). */
function hairline(rw: number): number {
    return Math.ceil(rw / TILE_UNITS);
}

/** An opponent's drawn tile's gap, a whole pixel. */
function drawnGap(rw: number): number {
    return Math.round(OPPONENT_DRAWN_GAP * rw);
}

/** A hand's length along its line (px): its tiles, whole-pixel hairlines between them and a drawn tile's gap. */
function handLength(tiles: number, drawn: boolean, rw: number): number {
    return tiles * rw + Math.max(0, tiles - 1) * hairline(rw) + (drawn ? drawnGap(rw) : 0);
}

function deepest(content: StripContent): number {
    return Math.max(UPRIGHT_DEPTH, ...content.melds.map((meld) => meld.depth));
}

/**
 * A side strip: the melds that fit its first line beside the hand, each within the room its own depth has, move
 * together to its far end as far as the tightest allows; from the first that does not fit, the oldest go to a second
 * line toward the table, scaled to fit beside the badge (never under the face floor) and aligned at the line's start or
 * end.
 */
function sideLayout(seat: "left" | "right", content: StripContent, rooms: StripRooms): StripLayout {
    const { gap, rw } = rooms;
    const { line, deepLine, secondLine, secondAt } = rooms[seat];
    const units = content.melds.map((meld) => meld.units);
    const lineRooms = content.melds.map((meld) => (meld.depth < SHALLOW_DEPTH ? line : deepLine));
    const count = units.length;
    const deep = deepest(content);
    const handLen = handLength(content.hand, content.drawn, rw);
    function before(index: number): number {
        return sum(units.slice(0, index));
    }
    const ends = units.map((_unit, index) => handLen + (index + 1) * gap + before(index + 1) * rw);
    const firstOver = ends.findIndex((end, index) => end > (lineRooms[index] ?? line));
    const wrapped = firstOver === -1 ? count : firstOver;
    const slack = ends.slice(0, wrapped).map((end, index) => (lineRooms[index] ?? line) - end);
    const shift = Math.max(0, Math.min(...slack));
    const secondUnits = Math.max(1, sum(units.slice(wrapped)));
    const secondRoom = secondLine - (count - wrapped - 1) * gap;
    const tile = Math.max(FACE_FLOOR, Math.min(secondRoom / secondUnits, rw));
    const secondStart = before(wrapped) * tile + wrapped * gap;
    const secondLen = sum(units) * tile + count * gap - secondStart - gap;
    const base = STRIP_POLICY[seat].second === "start" ? secondAt : secondAt - secondLen;
    const firstLine = Math.max(rw * TILE_ASPECT, count > 0 ? deep * rw : 0);
    const melds = units.map((_unit, index) =>
        index < wrapped
            ? { along: handLen + (index + 1) * gap + before(index) * rw + shift, rise: 0, tile: rw }
            : {
                  along: base + before(index) * tile + index * gap - secondStart,
                  rise: firstLine + STRIP_LINES_GAP,
                  tile,
              },
    );
    const oldest = content.melds.at(-1)?.depth ?? 0;
    const over = wrapped < count;
    return {
        depth: over ? firstLine + STRIP_LINES_GAP + oldest * rw : firstLine,
        melds,
        pull: 0,
    };
}

/**
 * The top strip: one line, its melds ending at its anchor at one size, the largest that keeps each above what it keeps
 * clear of where it stands (the top badge only for a meld reaching its lane) and fits them beside the hand, never under
 * the face floor; upright, a dense strip moves its anchor as far right as its melds at the face floor need, up to its
 * cap.
 */
function topLayout(content: StripContent, { gap, rw, top }: StripRooms): StripLayout {
    const { anchor, badgeDepth, cap, depth, lane, start } = top;
    const units = content.melds.map((meld) => meld.units);
    const count = units.length;
    const total = sum(units);
    const handLen = handLength(content.hand, content.drawn, rw);
    const heldLen = handLength(content.hand - (content.drawn ? 1 : 0), false, rw);
    const need = start + handLen + count * gap + total * FACE_FLOOR;
    const anchorAt = cap === null ? anchor : Math.min(cap, Math.max(anchor, need));
    const room = anchorAt - start;
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
    return { depth: 0, melds, pull: (cap ?? anchor) - anchorAt };
}

function stripLayout(seat: StripSeat, content: StripContent, rooms: StripRooms): StripLayout {
    return seat === "top" ? topLayout(content, rooms) : sideLayout(seat, content, rooms);
}

/** A strip's layout as lengths (px): its melds, the top strip's pull and a side strip's depth as drawn. */
function seatLengths(seat: StripSeat, { depth, melds, pull }: StripLayout): [string, number][] {
    const places = melds.flatMap(({ along, rise, tile }, index): [string, number][] => [
        [`${seat}-meld-${index}-along`, along],
        [`${seat}-meld-${index}-tile`, tile],
        [`${seat}-meld-${index}-rise`, rise],
    ]);
    const frame: Record<StripSeat, [string, number][]> = {
        left: [["left-depth", depth]],
        right: [["right-depth", depth]],
        top: [["top-pull", pull]],
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

export { STRIP_POLICY, drawnGap, hairline, handLength, stripLayout, stripLengths };
export type {
    MeldShape,
    MeldPlace,
    SideStripRoom,
    StripContent,
    StripLayout,
    StripRooms,
    StripSeat,
    TopStripRoom,
};
