import { SEAT_POSITIONS, type SeatPosition } from "@/entities/table/model/board-types";

import { FACE_FLOOR, TILE_ASPECT } from "./board-constants";
import {
    type BoardGeometry,
    type BoardInput,
    type BoardRect,
    type PlaneSpare,
    planeGeometry,
} from "./board-geometry";
import { CALLOUT_SPOTS } from "./callouts";

const DESKTOP_TILTS = [25, 22, 20, 18, 15, 12, 9, 6, 3, 0] as const;
const PHONE_TILTS = [15, 12, 9, 6, 3, 0] as const;

const CAMERA_WIDTHS = 2;

/** The river tile across the tilted core's middle stands within this share of the flat board's. */
const APPARENT_RIVER_SHARE = 0.05;

/** The camera may open at most this many flat river tiles of felt under the core beyond the flat board's spare. */
const OPENED_FELT_RIVERS = 2;

const CAP_STEPS = 4;

const PLANE_SOLVE_ROUNDS = 8;
const PLANE_TOLERANCE = 0.5;

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

type SideStrip = "strip-left" | "strip-right";

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

/** A piece's map from the plane to the board's layout: the camera's own at its anchor, linear around it. */
interface PieceMap {
    readonly anchor: PlanePoint;
    readonly shown: PlanePoint;
    readonly scale: number;
    readonly lean: number;
    readonly squash: number;
}

interface TableView {
    readonly camera: TableCamera;
    readonly plane: BoardGeometry;
    readonly pieces: Readonly<Record<TablePiece, BoardRect>>;
    readonly maps: Readonly<Record<TablePiece, PieceMap>>;
    /** The flat table's top on the board: at the board's foot under the tilted table, never centred in spare height. */
    readonly tableTop: number;
    readonly converged: boolean;
}

function radians({ tilt }: Pick<TableCamera, "tilt">): number {
    return (tilt * Math.PI) / 180;
}

function depthScale(camera: TableCamera, rise: number): number {
    return camera.distance / (camera.distance + rise * Math.sin(radians(camera)));
}

function projectPoint(camera: TableCamera, point: PlanePoint): PlanePoint {
    const rise = camera.planePivot.top - point.top;
    const scale = depthScale(camera, rise);
    return {
        left: camera.pivot.left + (point.left - camera.planePivot.left) * scale,
        top: camera.pivot.top - rise * Math.cos(radians(camera)) * scale,
    };
}

function laidRise(camera: Pick<TableCamera, "distance" | "tilt">, shown: number): number {
    const angle = radians(camera);
    return (
        (shown * camera.distance) / (Math.cos(angle) * camera.distance - shown * Math.sin(angle))
    );
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
        "river-right": rect([cx + hx + gap, cy + h - along, across, along]),
        "river-top": rect([cx + hx - along, cy - h - at("g-top") - across, along, across]),
        "strip-left": plane.areas["strip-left"] ?? none,
        "strip-right": plane.areas["strip-right"] ?? none,
        "strip-top": plane.areas["strip-top"] ?? none,
    };
}

type PieceHold = "far-edge" | "middle";

function pieceMap(camera: TableCamera, piece: BoardRect, hold: PieceHold = "middle"): PieceMap {
    const anchor = {
        left: (piece.left + piece.right) / 2,
        top: hold === "far-edge" ? piece.top : (piece.top + piece.bottom) / 2,
    };
    const rise = camera.planePivot.top - anchor.top;
    const scale = depthScale(camera, rise);
    const slope = (scale * scale * Math.sin(radians(camera))) / camera.distance;
    return {
        anchor,
        lean: (anchor.left - camera.planePivot.left) * slope,
        scale,
        shown: projectPoint(camera, anchor),
        squash: Math.cos(radians(camera)) * scale * scale,
    };
}

function mapPoint({ anchor, lean, scale, shown, squash }: PieceMap, point: PlanePoint): PlanePoint {
    const across = point.left - anchor.left;
    const down = point.top - anchor.top;
    return {
        left: shown.left + scale * across + lean * down,
        top: shown.top + squash * down,
    };
}

function corners({ bottom, left, right, top }: BoardRect): readonly PlanePoint[] {
    return [
        { left, top },
        { left: right, top },
        { left, top: bottom },
        { left: right, top: bottom },
    ];
}

function shownRect(map: PieceMap, piece: BoardRect): BoardRect {
    const shown = corners(piece).map((corner) => mapPoint(map, corner));
    return {
        bottom: Math.max(...shown.map(({ top }) => top)),
        left: Math.min(...shown.map(({ left }) => left)),
        right: Math.max(...shown.map(({ left }) => left)),
        top: Math.min(...shown.map(({ top }) => top)),
    };
}

function shifted(map: PieceMap, by: PlanePoint): PieceMap {
    return { ...map, shown: { left: map.shown.left + by.left, top: map.shown.top + by.top } };
}

/** How far a side strip shown at `shown` moves in to keep its outer edge no farther out than the flat board's. */
function outerFit(flat: BoardRect | undefined, seat: SideStrip, shown: BoardRect): number {
    if (flat === undefined) {
        return 0;
    }
    return seat === "strip-left"
        ? Math.max(0, flat.left - shown.left)
        : Math.min(0, flat.right - shown.right);
}

/**
 * A side strip's map kept on the board: its outer edge no farther out than the flat board's, and on a desktop its
 * near end above the own row's top (a phone's strips run on beside the own row).
 */
function fittedSide(
    view: { readonly screen: BoardGeometry; readonly phone: boolean },
    seat: SideStrip,
    { map, piece }: { readonly map: PieceMap; readonly piece: BoardRect },
): PieceMap {
    const shown = shownRect(map, piece);
    const outer = outerFit(view.screen.areas[seat], seat, shown);
    const ownRowTop = view.screen.lengths["foreground-top"] ?? shown.bottom;
    const lift = view.phone ? 0 : Math.min(0, ownRowTop - shown.bottom);
    return shifted(map, { left: outer, top: lift });
}

function tableMaps(
    camera: TableCamera,
    {
        phone,
        pieces,
        screen,
    }: { phone: boolean; pieces: Record<TablePiece, BoardRect>; screen: BoardGeometry },
): Record<TablePiece, PieceMap> {
    function map(piece: TablePiece): PieceMap {
        return pieceMap(camera, pieces[piece]);
    }
    function side(seat: SideStrip): PieceMap {
        const held = pieceMap(camera, pieces[seat], "far-edge");
        return fittedSide({ phone, screen }, seat, { map: held, piece: pieces[seat] });
    }
    const farEdge = pieceMap(camera, pieces["strip-top"], "far-edge");
    return {
        centre: map("centre"),
        dora: farEdge,
        "river-bottom": map("river-bottom"),
        "river-left": map("river-left"),
        "river-right": map("river-right"),
        "river-top": map("river-top"),
        "strip-left": side("strip-left"),
        "strip-right": side("strip-right"),
        "strip-top": farEdge,
    };
}

/** The flat table's top on the board: at the board's foot where the flat solve made it shorter than the board. */
function flatTableTop(screen: BoardGeometry, tilt: number): number {
    const tableHeight = screen.lengths["table-h"];
    if (tableHeight === undefined || tilt === 0) {
        return screen.lengths["table-top"] ?? 0;
    }
    return screen.box.height - tableHeight;
}

interface PlaneSolve {
    readonly camera: TableCamera;
    readonly plane: BoardGeometry;
    readonly tableTop: number;
    readonly converged: boolean;
}

/**
 * The tilted table at `tilt`: the board laid out on a plane box so much deeper that, with the camera's foot on the own
 * row's top, the plane's top shows at the board's top; the plane's own row's top found by rounds until it holds still.
 */
interface PlaneTarget {
    readonly input: BoardInput;
    readonly width: number;
    readonly cap: number;
    readonly ow: number;
    readonly spare: PlaneSpare;
    /** The plane's own row's top the camera needs, from the plane's top (px). */
    readonly wanted: number;
}

/** The plane box's depth found by rounds until its own row's top stands where the camera needs it. */
function settlePlane(
    target: PlaneTarget,
    start: number,
): { readonly plane: BoardGeometry; readonly converged: boolean } {
    const { cap, input, ow, spare, wanted, width } = target;
    let height = start;
    let plane = planeGeometry(input, { height, width }, { cap, ow, spare });
    for (let round = 0; round < PLANE_SOLVE_ROUNDS; round += 1) {
        const foot = plane.lengths["foreground-top"] ?? height;
        if (Math.abs(foot - wanted) < PLANE_TOLERANCE) {
            return { converged: true, plane };
        }
        height += wanted - foot;
        plane = planeGeometry(input, { height, width }, { cap, ow, spare });
    }
    return { converged: false, plane };
}

function solvePlane(
    input: BoardInput,
    screen: BoardGeometry,
    { cap, tilt }: { readonly cap: number; readonly tilt: number },
): PlaneSolve {
    const tableTop = flatTableTop(screen, tilt);
    const { height: boardHeight, width } = screen.box;
    const footShown = screen.lengths["foreground-top"] ?? boardHeight - tableTop;
    const lens = { distance: CAMERA_WIDTHS * width, tilt };
    const wanted = laidRise(lens, footShown + tableTop);
    const spare = screen.lengths["table-h"] === undefined ? "below-core" : "around-core";
    const target = { cap, input, ow: screen.lengths["ow"] ?? 1, spare, wanted, width } as const;
    const { converged, plane } = settlePlane(target, wanted + boardHeight - tableTop - footShown);
    return {
        camera: {
            ...lens,
            pivot: { left: width / 2, top: footShown },
            planePivot: {
                left: plane.box.width / 2,
                top: plane.lengths["foreground-top"] ?? wanted,
            },
        },
        converged,
        plane,
        tableTop,
    };
}

function apparentRiver(view: TableView): number {
    return (view.plane.lengths["rw"] ?? 0) * view.maps.centre.scale;
}

/** The least face an opponent's strip may lay: a phone's melds close their gaps down to the face floor. */
function stripFace(plane: BoardGeometry): number {
    return plane.family === "phone" ? FACE_FLOOR : (plane.lengths["rw"] ?? 0);
}

function farthestFace(view: TableView): { readonly short: number; readonly long: number } {
    const at = lengthOf(view.plane);
    const faces = [
        ...(["river-top", "river-left", "river-right"] as const).map((piece) => ({
            top: view.pieces[piece].top,
            width: at("rw"),
        })),
        { top: view.pieces["strip-top"].top, width: stripFace(view.plane) },
        { top: view.pieces.dora.top, width: at("dora-w") },
    ].map(({ top, width }) => {
        const scale = depthScale(view.camera, view.camera.planePivot.top - top);
        return width * Math.cos(radians(view.camera)) * scale * scale;
    });
    const short = Math.min(...faces);
    return { long: short * TILE_ASPECT, short };
}

function viewWithin(
    input: BoardInput,
    screen: BoardGeometry,
    { cap, tilt }: { readonly cap: number; readonly tilt: number },
): TableView {
    const { camera, converged, plane, tableTop } = solvePlane(input, screen, { cap, tilt });
    const pieces = tablePieces(plane);
    return {
        camera,
        converged,
        maps: tableMaps(camera, { phone: screen.family === "phone", pieces, screen }),
        pieces,
        plane,
        tableTop,
    };
}

/**
 * The view at `tilt` whose laid river tile shows across the core's middle no larger than the flat board's within the
 * band: the plane's largest tile, then one step smaller while it shows too large, a few steps at most.
 */
function viewAt(input: BoardInput, screen: BoardGeometry, tilt: number): TableView {
    const flatRiver = screen.lengths["rw"] ?? 1;
    const most = (1 + APPARENT_RIVER_SHARE) * flatRiver;
    let view = viewWithin(input, screen, { cap: 2 * flatRiver, tilt });
    for (let step = 0; step < CAP_STEPS && apparentRiver(view) > most; step += 1) {
        const cap = Math.min(
            (view.plane.lengths["rw"] ?? 1) - 1,
            Math.floor(most / view.maps.centre.scale),
        );
        view = viewWithin(input, screen, { cap, tilt });
    }
    return view;
}

/**
 * How much more felt the camera opens between the core's foot and the own row's top than the flat board shows there,
 * beyond the height the flat board leaves spare (a width-bound desktop's).
 */
function openedFelt(view: TableView, screen: BoardGeometry): number {
    const at = lengthOf(screen);
    const ownRowTop = at("foreground-top");
    const flatGap = ownRowTop - at("river-foot");
    const shownCore = Math.max(
        shownPiece(view, "river-bottom").bottom,
        shownPiece(view, "river-left").bottom,
        shownPiece(view, "river-right").bottom,
    );
    const flatSpare = screen.box.height - (screen.lengths["table-h"] ?? screen.box.height);
    return ownRowTop - shownCore - flatGap - flatSpare;
}

function holds(view: TableView, screen: BoardGeometry): boolean {
    const flatRiver = screen.lengths["rw"] ?? 0;
    const face = farthestFace(view);
    const floor = Math.min(FACE_FLOOR, flatRiver);
    return (
        view.converged &&
        openedFelt(view, screen) <= OPENED_FELT_RIVERS * flatRiver &&
        Math.abs(apparentRiver(view) - flatRiver) <= APPARENT_RIVER_SHARE * flatRiver &&
        face.short >= floor &&
        face.long >= Math.floor(floor * TILE_ASPECT)
    );
}

/**
 * The table as the camera shows it: the steepest tilt (25 degrees at most on a desktop, 15 on a phone, down to none)
 * whose plane solve settles, keeps the river tile across the core's middle within 5% of the flat board's and keeps its
 * farthest faces at the face floor.
 */
function tableView(input: BoardInput, screen: BoardGeometry): TableView {
    const tilts = screen.family === "phone" ? PHONE_TILTS : DESKTOP_TILTS;
    for (const tilt of tilts) {
        const view = viewAt(input, screen, tilt);
        if (tilt === 0 || holds(view, screen)) {
            return view;
        }
    }
    return viewAt(input, screen, 0);
}

function showPlanePoint(view: TableView, point: PlanePoint): PlanePoint {
    return projectPoint(view.camera, point);
}

function shownPiece(view: TableView, piece: TablePiece): BoardRect {
    return shownRect(view.maps[piece], view.pieces[piece]);
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

function plateAnchor(plane: BoardGeometry, seat: SeatPosition): PlanePoint {
    const at = lengthOf(plane);
    const inner = plane.box.width - at("plate-left-right");
    const anchors: Readonly<Record<SeatPosition, PlanePoint>> = {
        bottom: { left: at("plate-right-left"), top: at("plate-bottom-top") },
        left: { left: inner, top: at("plate-bottom-top") },
        right: { left: at("plate-right-left"), top: at("plate-top-top") },
        top: { left: inner, top: at("plate-top-top") },
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

/** A piece's CSS transform, from its own box's top left corner, onto the board's layout. */
function pieceTransform(map: PieceMap, piece: BoardRect, surfaceTop: number): string {
    const origin = mapPoint(map, { left: piece.left, top: piece.top });
    const values = [
        map.scale,
        0,
        map.lean,
        map.squash,
        origin.left - piece.left,
        origin.top - surfaceTop - piece.top,
    ];
    return `matrix(${values.join(", ")})`;
}

const SCREEN_ONLY_LENGTHS = new Set(["table-h", "table-top"]);

/** What the board takes from the camera: the flat table's place and the flat overlays' tilted anchors. */
function boardViewValues(view: TableView): [string, string][] {
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
            pointValues(`--geo-shown-centre-${corner}`, showPlanePoint(view, point)),
        ),
        ...SEAT_POSITIONS.flatMap((seat) =>
            pointValues(
                `--geo-shown-callout-${seat}`,
                showPlanePoint(view, calloutSpot(view.plane, seat)),
            ),
        ),
        ...SEAT_POSITIONS.flatMap((seat) =>
            pointValues(
                `--geo-shown-plate-${seat}`,
                showPlanePoint(view, plateAnchor(view.plane, seat)),
            ),
        ),
    ];
}

/** What the tilted surface takes: the plane's lengths and tracks, and each piece's transform. */
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
            pieceTransform(view.maps[piece], view.pieces[piece], -view.tableTop),
        ]),
    ];
}

export {
    TABLE_PIECES,
    apparentRiver,
    boardViewValues,
    farthestFace,
    projectPoint,
    showPlanePoint,
    shownPiece,
    surfaceViewValues,
    tableView,
};
export type { PieceMap, PlanePoint, TableCamera, TablePiece, TableView };
