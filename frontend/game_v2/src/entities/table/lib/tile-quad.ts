import { type MotionRect } from "./board-motion";

/** A point on the board's screen (px). */
export interface ScreenPoint {
    readonly left: number;
    readonly top: number;
}

/** A tile's four corners as the screen shows them: top left, top right, bottom right, bottom left. */
export type TileQuad = readonly [ScreenPoint, ScreenPoint, ScreenPoint, ScreenPoint];

/**
 * A projective map of the screen's plane: a point (x, y) goes to ((ax x + ay y + a0) / w, (bx x + by y + b0) / w), its
 * weight w = wx x + wy y + w0.
 */
export interface Homography {
    readonly ax: number;
    readonly ay: number;
    readonly a0: number;
    readonly bx: number;
    readonly by: number;
    readonly b0: number;
    readonly wx: number;
    readonly wy: number;
    readonly w0: number;
}

/**
 * A piece's CSS transform as its sixteen `matrix3d` values (column-major, as `DOMMatrix`'s m11 to m44 run), from its
 * box's top left corner.
 */
export type PieceMatrix = readonly number[];

/** A tilted piece's camera on the screen: its `matrix3d` and its box's top left corner. */
export interface PieceFrame {
    readonly matrix: PieceMatrix;
    readonly origin: ScreenPoint;
}

const IDENTITY: Homography = { a0: 0, ax: 1, ay: 0, b0: 0, bx: 0, by: 1, w0: 1, wx: 0, wy: 0 };

/** How far a quad's corner may stray from its rectangle's and still count as flat (px). */
const FLAT_TOLERANCE = 0.01;

/** How far a matrix's roll terms may stray from zero and still keep its rows level. */
const LEVEL_TOLERANCE = 1e-9;

/** A piece matrix's plane terms (its z column and row dropped) as a homography. */
function pieceHomography(matrix: PieceMatrix): Homography {
    function at(index: number): number {
        return matrix[index] ?? 0;
    }
    return {
        a0: at(12),
        ax: at(0),
        ay: at(4),
        b0: at(13),
        bx: at(1),
        by: at(5),
        w0: at(15),
        wx: at(3),
        wy: at(7),
    };
}

/** Where `warp` takes a point (px). */
export function warpPoint(warp: Homography, { left, top }: ScreenPoint): ScreenPoint {
    const weight = warp.wx * left + warp.wy * top + warp.w0;
    return {
        left: (warp.ax * left + warp.ay * top + warp.a0) / weight,
        top: (warp.bx * left + warp.by * top + warp.b0) / weight,
    };
}

/** The point `warp` takes to `point` (px). */
export function unwarpPoint(warp: Homography, point: ScreenPoint): ScreenPoint {
    const { a0, ax, ay, b0, bx, by, w0, wx, wy } = warp;
    return warpPoint(
        {
            a0: ay * b0 - a0 * by,
            ax: by * w0 - b0 * wy,
            ay: a0 * wy - ay * w0,
            b0: a0 * bx - ax * b0,
            bx: b0 * wx - bx * w0,
            by: ax * w0 - a0 * wx,
            w0: ax * by - ay * bx,
            wx: bx * wy - by * wx,
            wy: ay * wx - ax * wy,
        },
        point,
    );
}

/** A rectangle's corners, in a quad's order. */
export function rectQuad({ height, left, top, width }: MotionRect): TileQuad {
    return [
        { left, top },
        { left: left + width, top },
        { left: left + width, top: top + height },
        { left, top: top + height },
    ];
}

/**
 * Where a piece's box's top left corner stands on the board: the camera shows the box (`size`) inside `shown`, its
 * bounding box on the screen.
 */
export function pieceOrigin(
    matrix: PieceMatrix,
    size: Readonly<Record<"height" | "width", number>>,
    shown: MotionRect,
): ScreenPoint {
    const warp = pieceHomography(matrix);
    const corners = rectQuad({ height: size.height, left: 0, top: 0, width: size.width }).map(
        (corner) => warpPoint(warp, corner),
    );
    return {
        left: shown.left - Math.min(...corners.map(({ left }) => left)),
        top: shown.top - Math.min(...corners.map(({ top }) => top)),
    };
}

/** The row of a level-rowed piece's box that the screen shows at `top` (px). */
function rowAt(warp: Homography, top: number): number {
    return (warp.b0 - top * warp.w0) / (top * warp.wy - warp.by);
}

/** The column of a level-rowed piece's box that the screen shows at `left` on its row `row` (px). */
function columnAt(warp: Homography, left: number, row: number): number {
    return (left * (warp.wy * row + warp.w0) - warp.ay * row - warp.a0) / warp.ax;
}

/**
 * A tile's corners on a tilted piece, from its bounding box on the screen: the piece's camera keeps its rows level, so
 * the box's top and bottom are the tile's, and its sides the tile's near (wider) corners. Null where the matrix rolls
 * its rows, which no camera here does.
 */
export function tiltedQuad({ matrix, origin }: PieceFrame, shown: MotionRect): TileQuad | null {
    const warp = pieceHomography(matrix);
    if (Math.abs(warp.bx) > LEVEL_TOLERANCE || Math.abs(warp.wx) > LEVEL_TOLERANCE) {
        return null;
    }
    const box = { left: shown.left - origin.left, top: shown.top - origin.top };
    const rows = [rowAt(warp, box.top), rowAt(warp, box.top + shown.height)] as const;
    const first = Math.max(...rows.map((row) => columnAt(warp, box.left, row)));
    const last = Math.min(...rows.map((row) => columnAt(warp, box.left + shown.width, row)));
    function corner(left: number, top: number): ScreenPoint {
        const point = warpPoint(warp, { left, top });
        return { left: point.left + origin.left, top: point.top + origin.top };
    }
    const [far, near] = rows;
    return [corner(first, far), corner(last, far), corner(last, near), corner(first, near)];
}

/** The map from the unit square onto `quad`, its corners in order (Heckbert's square-to-quad). */
function squareToQuad([first, second, third, fourth]: TileQuad): Homography {
    const sumLeft = first.left - second.left + third.left - fourth.left;
    const sumTop = first.top - second.top + third.top - fourth.top;
    const [acrossLeft, acrossTop] = [second.left - third.left, second.top - third.top];
    const [downLeft, downTop] = [fourth.left - third.left, fourth.top - third.top];
    const determinant = acrossLeft * downTop - downLeft * acrossTop;
    const wx = (sumLeft * downTop - downLeft * sumTop) / determinant;
    const wy = (acrossLeft * sumTop - sumLeft * acrossTop) / determinant;
    return {
        a0: first.left,
        ax: second.left - first.left + wx * second.left,
        ay: fourth.left - first.left + wy * fourth.left,
        b0: first.top,
        bx: second.top - first.top + wx * second.top,
        by: fourth.top - first.top + wy * fourth.top,
        w0: 1,
        wx,
        wy,
    };
}

/** Whether `quad` is the rectangle `rect`. */
function isRect(quad: TileQuad, rect: MotionRect): boolean {
    const corners = rectQuad(rect);
    return quad.every(
        (corner, index) =>
            Math.abs(corner.left - corners[index].left) < FLAT_TOLERANCE &&
            Math.abs(corner.top - corners[index].top) < FLAT_TOLERANCE,
    );
}

/**
 * What takes a tile's bounding box `rect`, centred on its own centre, onto its corners `quad` relative to that centre:
 * the taper and squash a flat image of the box needs to show the tile as the camera does (the identity on a flat
 * piece).
 */
export function quadWarp(rect: MotionRect, quad: TileQuad): Homography {
    if (isRect(quad, rect)) {
        return IDENTITY;
    }
    const centre = { left: rect.left + rect.width / 2, top: rect.top + rect.height / 2 };
    const [first, second, third, fourth] = quad.map(({ left, top }) => ({
        left: left - centre.left,
        top: top - centre.top,
    }));
    const square = squareToQuad([first, second, third, fourth]);
    const [across, down] = [1 / rect.width, 1 / rect.height];
    return {
        a0: (square.ax + square.ay) / 2 + square.a0,
        ax: square.ax * across,
        ay: square.ay * down,
        b0: (square.bx + square.by) / 2 + square.b0,
        bx: square.bx * across,
        by: square.by * down,
        w0: (square.wx + square.wy) / 2 + square.w0,
        wx: square.wx * across,
        wy: square.wy * down,
    };
}

/** `warp` as a CSS `matrix3d`, acting on its element's box about its centre. */
export function warpTransform(warp: Homography): string {
    const { a0, ax, ay, b0, bx, by, w0, wx, wy } = warp;
    const values = [ax, bx, 0, wx, ay, by, 0, wy, 0, 0, 1, 0, a0, b0, 0, w0].map(
        (value) => value / w0,
    );
    return `matrix3d(${values.join(", ")})`;
}
