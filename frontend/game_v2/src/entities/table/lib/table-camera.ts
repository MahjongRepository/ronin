import { SEAT_POSITIONS, type SeatPosition } from "@/entities/table/model/board-types";

import { TILE_ASPECT, TOP_HAND_EDGE_SHARE, UPRIGHT_DEPTH } from "./board-constants";
import { type BoardGeometry, type BoardRect } from "./board-geometry";
import { CALLOUT_SPOTS } from "./callouts";

const CAMERA_WIDTHS = 2;

/**
 * A plate's riichi stick hangs this far under its pill (px), as long as the centre's stick (this share of the centre's
 * side) but never shorter than this many of the plate's text, at 6/48 tall.
 */
const STICK_DROP = 3;
const STICK_LENGTH_BY_CENTRE = 0.45;
const STICK_LENGTH_BY_TEXT = 2.2;
const STICK_ASPECT = 6 / 48;

/** A riichi stick keeps at least this far off the core under it on a desktop, and on a phone (px). */
const STICK_GAP = 10;
const PHONE_STICK_GAP = 6;

const TABLE_PIECES = [
    "centre",
    "dora",
    "river-bottom",
    "river-right",
    "river-top",
    "river-left",
    "strip-top",
    "strip-right",
    "strip-left",
] as const;

type TablePiece = (typeof TABLE_PIECES)[number];

interface PlanePoint {
    readonly left: number;
    readonly top: number;
}

/**
 * One camera over the table: tilted `tilt` degrees, `distance` px from the screen, its foot (`planePivot` on the plane)
 * shown at `pivot` on the board's layout.
 */
interface TableCamera {
    readonly tilt: number;
    readonly distance: number;
    readonly pivot: PlanePoint;
    readonly planePivot: PlanePoint;
}

interface TableView {
    readonly camera: TableCamera;
    readonly plane: BoardGeometry;
    readonly pieces: Readonly<Record<TablePiece, BoardRect>>;
    /** What each piece moves by on the plane before the camera, to keep a side strip inside its flat place. */
    readonly shifts: Readonly<Record<TablePiece, PlanePoint>>;
    /** The flat table's top on the board; the tilted table's top shows `margin` under it. */
    readonly tableTop: number;
    readonly margin: number;
    /**
     * Where a phone's counters stand flat on the layout (its corner card stays chrome, its tiles at the face floor
     * already); a desktop's tilt with the table.
     */
    readonly flatCounters: PlanePoint | null;
    readonly converged: boolean;
    /** How much wider a phone's plane lays the felt under its top strip's meld room than the flat board (px). */
    readonly topGap: number;
}

function lengthOf(geometry: BoardGeometry): (name: string) => number {
    return function at(name: string): number {
        return geometry.lengths[name] ?? 0;
    };
}

function rect([left, top, width, height]: readonly [number, number, number, number]): BoardRect {
    return { bottom: top + height, left, right: left + width, top };
}

function tablePieces(plane: BoardGeometry): Record<TablePiece, BoardRect> {
    const at = lengthOf(plane);
    const [cx, cy, hx, h, gap] = [at("cx"), at("cy"), at("hx"), at("h"), at("g")];
    const along = at("river-along");
    const across = at("river-across");
    const none = rect([0, 0, 0, 0]);
    return {
        centre: rect([cx - hx, cy - h, at("w"), at("c")]),
        dora: rect([at("counters-x"), at("counters-top"), at("counters-w"), at("counters-h")]),
        "river-bottom": rect([cx - hx, cy + h + gap, along, across]),
        "river-left": rect([cx - hx - gap - across, cy - h, across, along]),
        "river-right": rect([
            cx + hx + gap,
            cy + h - at("river-right-lift") - along,
            across,
            along,
        ]),
        "river-top": rect([cx + hx - along, cy - h - at("g-top") - across, along, across]),
        "strip-left": plane.areas["strip-left"] ?? none,
        "strip-right": plane.areas["strip-right"] ?? none,
        "strip-top": plane.areas["strip-top"] ?? none,
    };
}

/** Every piece where its plane lays it. */
function stillShifts(): Record<TablePiece, PlanePoint> {
    const still = { left: 0, top: 0 };
    return {
        centre: still,
        dora: still,
        "river-bottom": still,
        "river-left": still,
        "river-right": still,
        "river-top": still,
        "strip-left": still,
        "strip-right": still,
        "strip-top": still,
    };
}

function tableView(screen: BoardGeometry): TableView {
    const at = lengthOf(screen);
    const footShown = at("foreground-top");
    const camera = {
        distance: CAMERA_WIDTHS * screen.box.width,
        pivot: { left: screen.box.width / 2, top: footShown },
        planePivot: { left: screen.box.width / 2, top: footShown },
        tilt: 0,
    };
    return {
        camera,
        converged: true,
        flatCounters: null,
        margin: 0,
        pieces: tablePieces(screen),
        plane: screen,
        shifts: stillShifts(),
        tableTop: screen.lengths["table-top"] ?? 0,
        topGap: 0,
    };
}

function calloutSpot(plane: BoardGeometry, seat: SeatPosition): PlanePoint {
    const at = lengthOf(plane);
    const [along, across] = CALLOUT_SPOTS[seat];
    const [cx, cy, hx, h, gap, rw, rh] = ["cx", "cy", "hx", "h", "g", "rw", "rh"].map(at);
    const spots: Readonly<Record<SeatPosition, PlanePoint>> = {
        bottom: { left: cx - hx + along * rw, top: cy + h + gap + across * rh },
        left: { left: cx - hx - gap - across * rh, top: cy - h + along * rw },
        right: { left: cx + hx + gap + across * rh, top: cy + h - along * rw },
        top: { left: cx + hx - along * rw, top: cy - h - at("g-top") - across * rh },
    };
    return spots[seat];
}

/** Whether a seat's plate stands in the top row of plates (over the core's top corners) or the bottom row. */
function topRowPlate(seat: SeatPosition): boolean {
    return seat === "top" || seat === "right";
}

/**
 * A plate's anchor: its inner edge at its box's edge toward the rivers beside it (a top row plate's bottom, its riichi
 * stick's side; a bottom row plate's top), which the flat plate then stands on, so the camera keeps that edge's gap.
 */
function plateAnchor(plane: BoardGeometry, seat: SeatPosition): PlanePoint {
    const at = lengthOf(plane);
    const inner = plane.box.width - at("plate-left-right");
    const height = at("badge-h");
    const anchors: Readonly<Record<SeatPosition, PlanePoint>> = {
        bottom: { left: at("plate-right-left"), top: at("plate-bottom-top") },
        left: { left: inner, top: at("plate-bottom-top") },
        right: { left: at("plate-right-left"), top: at("plate-top-top") + height },
        top: { left: inner, top: at("plate-top-top") + height },
    };
    return anchors[seat];
}

function px(value: number): string {
    return `${value}px`;
}

function pointValues(name: string, { left, top }: PlanePoint): [string, string][] {
    return [
        [`${name}-x`, px(left)],
        [`${name}-y`, px(top)],
    ];
}

function pieceTransform(view: TableView): string {
    return view.tableTop === 0 ? "none" : `translate(0px, ${px(view.tableTop)})`;
}

/** The tallest a top hand's standing back shows, in its widths, whatever the camera's tilt. */
const TOP_BACK_SHOWN_ASPECT = 1.52;

function topHandValues(view: TableView): [string, string][] {
    const depth = UPRIGHT_DEPTH + TOP_HAND_EDGE_SHARE;
    const foot = depth * (view.plane.lengths["rw"] ?? 0);
    const concealedDown = Math.min(1, TOP_BACK_SHOWN_ASPECT / depth);
    function standingOnFoot(down: number): string {
        return `matrix(1, 0, 0, ${down}, 0, ${view.tableTop + foot * (1 - down)})`;
    }
    return [
        ["--geo-camera-top-hand", standingOnFoot(concealedDown)],
        ["--geo-camera-top-hand-revealed", standingOnFoot(1)],
        ["--geo-top-hand-back-scale", String(concealedDown)],
    ];
}

const SCREEN_ONLY_LENGTHS = new Set(["table-h", "table-top"]);

function platePlace(view: TableView, screen: BoardGeometry, seat: SeatPosition): PlanePoint {
    const shown = plateAnchor(view.plane, seat);
    if (!topRowPlate(seat)) {
        return { left: shown.left, top: shown.top };
    }
    const top = shown.top - (screen.lengths["badge-h"] ?? 0);
    const stick = stickUnder(screen, { left: shown.left, seat, top });
    const nearest = Math.min(
        Infinity,
        ...(["centre", "river-left", "river-right", "river-top"] as const)
            .map((piece) => shownReach(view, piece))
            .filter(
                (piece) =>
                    piece.left < stick.right &&
                    stick.left < piece.right &&
                    piece.bottom > stick.foot - 1,
            )
            .map((piece) => piece.top),
    );
    const least = screen.family === "phone" ? PHONE_STICK_GAP : STICK_GAP;
    return { left: shown.left, top: top - Math.ceil(Math.max(0, stick.foot + least - nearest)) };
}

/**
 * A piece as far as its tiles can reach on the screen: a river row holding a sideways riichi tile runs a tile's height
 * instead of its width, past the river's box on the side it runs to (the right river's top, the top river's left).
 */
function shownReach(
    view: TableView,
    piece: "centre" | "river-left" | "river-right" | "river-top",
): BoardRect {
    const flat = view.pieces[piece];
    const sideways = (TILE_ASPECT - 1) * (view.plane.lengths["rw"] ?? 0);
    if (piece === "river-right") {
        return { ...flat, top: flat.top - sideways };
    }
    if (piece === "river-top") {
        return { ...flat, left: flat.left - sideways };
    }
    return flat;
}

/**
 * A top row plate's riichi stick's foot and the span its plate covers, for its plate's box at `top`: the pill centred
 * in the box, the stick hanging under it.
 */
function stickUnder(
    screen: BoardGeometry,
    {
        left,
        seat,
        top,
    }: { readonly left: number; readonly seat: SeatPosition; readonly top: number },
): { readonly foot: number; readonly left: number; readonly right: number } {
    const at = lengthOf(screen);
    const pillTop = top + (at("badge-h") - at("pill-h")) / 2;
    const reachesLeft = seat === "top";
    return {
        foot:
            pillTop +
            at("pill-h") +
            STICK_DROP +
            Math.max(STICK_LENGTH_BY_TEXT * at("text"), STICK_LENGTH_BY_CENTRE * at("c")) *
                STICK_ASPECT,
        left: reachesLeft ? left - at("plate-w") : left,
        right: reachesLeft ? left : left + at("plate-w"),
    };
}

function boardViewValues(view: TableView, screen: BoardGeometry): [string, string][] {
    const { centre } = view.pieces;
    const shownCorners = {
        bl: { left: centre.left, top: centre.bottom },
        br: { left: centre.right, top: centre.bottom },
        tl: { left: centre.left, top: centre.top },
        tr: { left: centre.right, top: centre.top },
    };
    return [
        ["--geo-table-top", px(view.tableTop)],
        ...Object.entries(shownCorners).flatMap(([corner, point]) =>
            pointValues(`--geo-shown-centre-${corner}`, point),
        ),
        ...SEAT_POSITIONS.flatMap((seat) =>
            pointValues(`--geo-shown-callout-${seat}`, calloutSpot(view.plane, seat)),
        ),
        ...SEAT_POSITIONS.flatMap((seat) =>
            pointValues(`--geo-shown-plate-${seat}`, platePlace(view, screen, seat)),
        ),
    ];
}

function surfaceViewValues(view: TableView): [string, string][] {
    const { plane } = view;
    return [
        ...Object.entries(plane.lengths)
            .filter(([name]) => !SCREEN_ONLY_LENGTHS.has(name))
            .map(([name, length]): [string, string] => [`--geo-${name}`, px(length)]),
        ["--geo-shell-columns", plane.tracks.columns],
        ["--geo-shell-rows", plane.tracks.rows],
        ...TABLE_PIECES.map((piece): [string, string] => [
            `--geo-camera-${piece}`,
            pieceTransform(view),
        ]),
        ...topHandValues(view),
    ];
}

export { boardViewValues, surfaceViewValues, tableView };
export type { TableView };
