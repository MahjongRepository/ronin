import { SEAT_POSITIONS, type SeatPosition } from "@/entities/table/model/board-types";

import { LYING_Y_SHARE, TILE_ASPECT, TOP_HAND_EDGE_SHARE } from "./board-constants";
import { type BoardGeometry, type BoardRect } from "./board-geometry";
import { CALLOUT_SPOTS } from "./callouts";

const CAMERA_WIDTHS = 2;

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
    const sideAlong = at("side-river-along");
    const sideAcross = at("side-river-across");
    const none = rect([0, 0, 0, 0]);
    return {
        centre: rect([cx - hx, cy - h, at("w"), at("c")]),
        dora: rect([at("counters-x"), at("counters-top"), at("counters-w"), at("counters-h")]),
        "river-bottom": rect([cx - hx, cy + h + gap, along, across]),
        "river-left": rect([cx - hx - gap - sideAcross, cy - h, sideAcross, sideAlong]),
        "river-right": rect([
            cx + hx + gap,
            cy + h - at("river-right-lift") - sideAlong,
            sideAcross,
            sideAlong,
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
    const [downRw, downRh] = [rw * LYING_Y_SHARE, rh * LYING_Y_SHARE];
    const spots: Readonly<Record<SeatPosition, PlanePoint>> = {
        bottom: { left: cx - hx + along * rw, top: cy + h + gap + across * downRh },
        left: { left: cx - hx - gap - across * rh, top: cy - h + along * downRw },
        right: { left: cx + hx + gap + across * rh, top: cy + h - along * downRw },
        top: { left: cx + hx - along * rw, top: cy - h - at("g-top") - across * downRh },
    };
    return spots[seat];
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
const TOP_BACK_SHOWN_ASPECT = 1.38;

function topHandValues(view: TableView): [string, string][] {
    const depth = TILE_ASPECT + TOP_HAND_EDGE_SHARE;
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

function boardViewValues(view: TableView): [string, string][] {
    const { centre, "strip-left": stripLeft, "strip-right": stripRight } = view.pieces;
    const shownCorners = {
        bl: { left: centre.left, top: centre.bottom },
        br: { left: centre.right, top: centre.bottom },
        tl: { left: centre.left, top: centre.top },
        tr: { left: centre.right, top: centre.top },
    };
    return [
        ["--geo-table-top", px(view.tableTop)],
        ["--geo-shown-lane-left-x", px(stripLeft.right)],
        ["--geo-shown-lane-right-x", px(stripRight.left)],
        ...Object.entries(shownCorners).flatMap(([corner, point]) =>
            pointValues(`--geo-shown-centre-${corner}`, point),
        ),
        ...SEAT_POSITIONS.flatMap((seat) =>
            pointValues(`--geo-shown-callout-${seat}`, calloutSpot(view.plane, seat)),
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
