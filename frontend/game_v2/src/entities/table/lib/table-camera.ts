import { SEAT_POSITIONS, type SeatPosition } from "@/entities/table/model/board-types";

import {
    FACE_FLOOR,
    STACKED_DEPTH,
    TILE_ASPECT,
    TILE_EDGE_SHARE,
    TOP_CORE_CLEAR,
    UPRIGHT_DEPTH,
} from "./board-constants";
import {
    type BoardGeometry,
    type BoardInput,
    type BoardRect,
    type PlaneSpare,
    planeGeometry,
} from "./board-geometry";
import { CALLOUT_SPOTS } from "./callouts";

const DESKTOP_TILTS = [20, 18, 15, 12, 10] as const;
const PHONE_TILTS = [15, 12, 10] as const;

const CAMERA_WIDTHS = 2;

/** The river tile across the tilted core's middle shows within this share of the flat board's. */
const APPARENT_RIVER_SHARE = 0.05;

/** The nearest river tile shows at most this share of the own tile, so the own hand stays the table's largest. */
const NEAR_RIVER_BY_OWN = 0.85;

/** A felt band between the table's pieces may open at most this many flat river tiles wider than the flat board's. */
const BAND_RIVERS = 0.95;

/** How much narrower than the flat board's the camera may show the felt between the top hand and the top river (px). */
const BAND_SLACK = 1;

/** On a desktop, that felt may show this many flat river tiles narrower, where that is more than `BAND_SLACK`. */
const TOP_BAND_SLACK_RIVERS = 0.1;

/** A plate's riichi stick hangs this far under its pill (px), as long as this many of the plate's text, at 6/32 tall. */
const STICK_DROP = 3;
const STICK_LENGTH_BY_TEXT = 2.2;
const STICK_ASPECT = 6 / 32;

/** A riichi stick keeps at least this far off the core under it on a desktop, and on a phone (px). */
const STICK_GAP = 10;
const PHONE_STICK_GAP = 6;

/** The felt the camera keeps between the core and the own row's top at least, where the flat board keeps more (px). */
const BOTTOM_BAND_LEAST = 4;

/** Felt the bands cannot hold may lie over the table's top, at most this many flat river tiles of it. */
const MARGIN_RIVERS = 0.15;

/** The decisions' band keeps this far off the core's tiles (px), as the visual check's least. */
const BAND_CLEAR = 4;

/** A desktop's side strip's farthest tile keeps at least this far off the top strip's nearest tile, or the flat gap (px). */
const SIDE_TOP_CLEAR = 16;

/** A desktop's counters keep at least this far off the top strip's first tile (px). */
const COUNTERS_CLEAR = 8;

const CAP_STEPS = 4;

const PLANE_SPARE: PlaneSpare = "around-core";
const PHONE_FLOOR_ROUNDS = 8;

/** A tilted strip's farthest face shows this far over the face floor (px). */
const TILTED_FACE_MARGIN = 1;

/** A phone's plane may lay its undrawn own row this much narrower than the flat one to keep its river tile. */
const PLANE_OWN_LEAST = 0.85;

const PLANE_SOLVE_ROUNDS = 8;
/** The top margin is found to this much, and the bands' overflow counted from it (px). */
const MARGIN_TOLERANCE = 0.5;
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

/** How a piece's tiles lie on the screen: along its rows (the top and bottom), or turned (the sides). */
type PieceFacing = "along" | "turned";

const FACINGS: Readonly<Record<TablePiece, PieceFacing>> = {
    centre: "along",
    dora: "along",
    "river-bottom": "along",
    "river-left": "turned",
    "river-right": "turned",
    "river-top": "along",
    "strip-left": "turned",
    "strip-right": "turned",
    "strip-top": "along",
};

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

type Matrix3 = readonly [
    readonly [number, number, number],
    readonly [number, number, number],
    readonly [number, number, number],
];

function radians({ tilt }: Pick<TableCamera, "tilt">): number {
    return (tilt * Math.PI) / 180;
}

function depthScale(camera: TableCamera, rise: number): number {
    return camera.distance / (camera.distance + rise * Math.sin(radians(camera)));
}

/** How large the camera shows a length at the plane's `top`: across the screen, and down it. */
function scalesAt(
    camera: TableCamera,
    top: number,
): { readonly across: number; readonly down: number } {
    const across = depthScale(camera, camera.planePivot.top - top);
    return { across, down: Math.cos(radians(camera)) * across * across };
}

function projectPoint(camera: TableCamera, point: PlanePoint): PlanePoint {
    const rise = camera.planePivot.top - point.top;
    const scale = depthScale(camera, rise);
    return {
        left: camera.pivot.left + (point.left - camera.planePivot.left) * scale,
        top: camera.pivot.top - rise * Math.cos(radians(camera)) * scale,
    };
}

/** The camera as a plane-to-layout homography on (left, top, 1). */
function homography(camera: TableCamera): Matrix3 {
    const sine = Math.sin(radians(camera));
    const cosine = Math.cos(radians(camera));
    const { distance, pivot, planePivot } = camera;
    const far = distance + planePivot.top * sine;
    return [
        [distance, -pivot.left * sine, pivot.left * far - distance * planePivot.left],
        [
            0,
            distance * cosine - pivot.top * sine,
            pivot.top * far - distance * cosine * planePivot.top,
        ],
        [0, -sine, far],
    ];
}

function multiply(first: Matrix3, second: Matrix3): Matrix3 {
    function cell(row: number, column: number): number {
        return (
            first[row][0] * second[0][column] +
            first[row][1] * second[1][column] +
            first[row][2] * second[2][column]
        );
    }
    return [
        [cell(0, 0), cell(0, 1), cell(0, 2)],
        [cell(1, 0), cell(1, 1), cell(1, 2)],
        [cell(2, 0), cell(2, 1), cell(2, 2)],
    ];
}

function translation({ left, top }: PlanePoint): Matrix3 {
    return [
        [1, 0, left],
        [0, 1, top],
        [0, 0, 1],
    ];
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

function corners({ bottom, left, right, top }: BoardRect): readonly PlanePoint[] {
    return [
        { left, top },
        { left: right, top },
        { left, top: bottom },
        { left: right, top: bottom },
    ];
}

function boundsOf(points: readonly PlanePoint[]): BoardRect {
    return {
        bottom: Math.max(...points.map(({ top }) => top)),
        left: Math.min(...points.map(({ left }) => left)),
        right: Math.max(...points.map(({ left }) => left)),
        top: Math.min(...points.map(({ top }) => top)),
    };
}

function shownRect(camera: TableCamera, piece: BoardRect, shift: PlanePoint): BoardRect {
    return boundsOf(
        corners(piece).map((corner) =>
            projectPoint(camera, { left: corner.left + shift.left, top: corner.top + shift.top }),
        ),
    );
}

/** How far a side strip moves on the screen to keep its outer edge no farther out than the flat board's. */
function outerFit(flat: BoardRect | undefined, seat: SideStrip, shown: BoardRect): number {
    if (flat === undefined) {
        return 0;
    }
    return seat === "strip-left"
        ? Math.max(0, flat.left - shown.left)
        : Math.min(0, flat.right - shown.right);
}

/**
 * A side strip's move on the plane: on a desktop its near end no lower than the plane's own row's top (a phone's strips
 * run on beside the own row), then across so its outer edge, shown at its near end, stands no farther out than the
 * flat board's.
 */
function sideShift(
    camera: TableCamera,
    { phone, screen }: { readonly screen: BoardGeometry; readonly phone: boolean },
    { piece, seat }: { readonly piece: BoardRect; readonly seat: SideStrip },
): PlanePoint {
    const top = phone ? 0 : Math.min(0, camera.planePivot.top - piece.bottom);
    const shown = shownRect(camera, piece, { left: 0, top });
    const { across } = scalesAt(camera, piece.bottom + top);
    return { left: outerFit(screen.areas[seat], seat, shown) / across, top };
}

/** A table as a camera shows it: its plane's pieces, each moved by its shift. */
type SeenTable = Pick<TableView, "camera" | "pieces" | "plane" | "shifts">;

/** How far in from its box's left edge the top strip's melds end (px). */
function topInsetOf({ plane }: Pick<SeenTable, "plane">): number {
    return plane.strips?.top.inset ?? 0;
}

/**
 * Where the top strip's end tile by `seat` shows its outer foot corner, at its line's stacked depth: the left end may
 * hold a meld (a kan stacked) as far out as its line starts, the right end the hand.
 */
function stripEndFoot(table: SeenTable, seat: SideStrip): PlanePoint {
    const strip = table.pieces["strip-top"];
    const edge = seat === "strip-left" ? strip.left + topInsetOf(table) : strip.right;
    return projectPoint(table.camera, { left: edge, top: strip.bottom });
}

/** Where a side strip's farthest tile shows its inner corner: it lies on the lane's outer edge, a tile's length deep. */
function sideFarCorner({ camera, pieces, plane, shifts }: SeenTable, seat: SideStrip): PlanePoint {
    const side = pieces[seat];
    const deep = (TILE_ASPECT + TILE_EDGE_SHARE) * (plane.lengths["rw"] ?? 0);
    const edge = seat === "strip-left" ? side.left + deep : side.right - deep;
    return projectPoint(camera, {
        left: edge + shifts[seat].left,
        top: side.top + shifts[seat].top,
    });
}

/** How far a side strip's farthest tile shows off the top strip's end tile beside it, as two boxes' gap. */
function sideTopGap(table: SeenTable, seat: SideStrip): number {
    const foot = stripEndFoot(table, seat);
    const corner = sideFarCorner(table, seat);
    const across = seat === "strip-left" ? foot.left - corner.left : corner.left - foot.left;
    return Math.max(across, corner.top - foot.top);
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

/** The gap a side strip's farthest tile keeps off the top strip's: the flat board's, to `SIDE_TOP_CLEAR`. */
function sideTopWanted(screen: BoardGeometry, seat: SideStrip): number {
    return Math.min(SIDE_TOP_CLEAR, sideTopGap(flatView(screen), seat));
}

/**
 * The gap the counters keep off the top strip's first tile: the flat board's, or the plane's where its card differs,
 * never under `COUNTERS_CLEAR`.
 */
function countersWanted(pieces: Record<TablePiece, BoardRect>, screen: BoardGeometry): number {
    const flat = tablePieces(screen);
    return Math.max(
        COUNTERS_CLEAR,
        Math.min(
            flat["strip-top"].left - flat.dora.right,
            pieces["strip-top"].left - pieces.dora.right,
        ),
    );
}

/**
 * How far right the camera must show the top strip's left end for the left strip's farthest tile and the counters
 * (which show their wanted gap's left edge at `counters`) to keep their gaps off it, or -Infinity (px).
 */
function topLeftNeeds(table: SeenTable, screen: BoardGeometry, counters: number): number {
    const foot = stripEndFoot(table, "strip-left");
    const corner = sideFarCorner(table, "strip-left");
    const wanted = sideTopWanted(screen, "strip-left");
    const side = corner.top - foot.top >= wanted ? -Infinity : corner.left + wanted - foot.left;
    return Math.max(side, counters - foot.left);
}

/**
 * How far in the top strip's line starts on the plane: where the side strips or the counters stand in under its left
 * end, the least that shows each its wanted gap off the melds lying there; its hand, at the line's right end, never
 * moves.
 */
function topInset(table: SeenTable, screen: BoardGeometry, counters: number): number {
    const { across } = scalesAt(table.camera, table.pieces["strip-top"].bottom);
    return Math.max(0, topLeftNeeds(table, screen, counters) / across);
}

/** `plane` with its top strip's line starting `inset` further in. */
function insetTopLine(plane: BoardGeometry, inset: number): BoardGeometry {
    const { strips } = plane;
    if (strips === null || inset === 0) {
        return plane;
    }
    return {
        ...plane,
        strips: { ...strips, top: { ...strips.top, inset } },
    };
}

/**
 * The counters' move on the plane: across, away from the top strip, so the camera shows them `countersWanted` off its
 * first tile, never past the flat counters' left edge (the top strip moves on for what that leaves short).
 */
function countersShift(table: SeenTable, screen: BoardGeometry): PlanePoint {
    const { camera, pieces } = table;
    const { dora } = pieces;
    const shownRight = projectPoint(camera, { left: dora.right, top: dora.top }).left;
    const shownLeft = projectPoint(camera, { left: dora.left, top: dora.bottom }).left;
    const room =
        Math.min(0, tablePieces(screen).dora.left - shownLeft) /
        scalesAt(camera, dora.bottom).across;
    const gap = stripEndFoot(table, "strip-left").left - shownRight;
    const needed =
        Math.min(0, gap - countersWanted(pieces, screen)) / scalesAt(camera, dora.top).across;
    return { left: Math.max(needed, room), top: 0 };
}

/**
 * Each piece's move on the plane (the side strips' to their flat places, then on a desktop the counters' off the top
 * strip) and the plane with the top strip's line starting clear of the side strips and the counters.
 */
function laidTable(
    camera: TableCamera,
    {
        phone,
        pieces,
        plane,
        screen,
    }: Omit<SeenTable, "camera" | "shifts"> & {
        readonly phone: boolean;
        readonly screen: BoardGeometry;
    },
): Pick<SeenTable, "plane" | "shifts"> {
    function side(seat: SideStrip): PlanePoint {
        return sideShift(camera, { phone, screen }, { piece: pieces[seat], seat });
    }
    const shifts = {
        ...stillShifts(),
        "strip-left": side("strip-left"),
        "strip-right": side("strip-right"),
    };
    if (phone) {
        return { plane, shifts };
    }
    const table = { camera, pieces, plane, shifts };
    const dora = countersShift(table, screen);
    const counters =
        projectPoint(camera, { left: pieces.dora.right + dora.left, top: pieces.dora.top }).left +
        countersWanted(pieces, screen);
    return {
        plane: insetTopLine(plane, topInset(table, screen, counters)),
        shifts: { ...shifts, dora },
    };
}

interface PlaneAt {
    readonly cap: number;
    readonly tilt: number;
    readonly faceFloor?: number;
    readonly topGap?: number;
    /** How far below the flat table's top the tilted table's top shows: the felt its bands could not hold (px). */
    readonly margin?: number;
    /** The own tile the plane lays its (undrawn) own row at; the flat board's when not given. */
    readonly ow?: number;
    readonly coreLift?: number;
}

interface PlaneTarget extends PlaneAt {
    readonly input: BoardInput;
    readonly width: number;
    readonly ow: number;
    readonly spare: PlaneSpare;
    readonly beside?: boolean;
    /** The plane's own row's top the camera needs, from the plane's top (px). */
    readonly wanted: number;
}

/** The plane box's depth found by rounds until its own row's top stands where the camera needs it. */
function settlePlane(
    target: PlaneTarget,
    start: number,
): { readonly plane: BoardGeometry; readonly converged: boolean } {
    const { beside, cap, coreLift, faceFloor, input, ow, spare, topGap, wanted, width } = target;
    let height = start;
    let plane = planeGeometry(
        input,
        { height, width },
        { beside, cap, coreLift, faceFloor, ow, spare, topGap },
    );
    for (let round = 0; round < PLANE_SOLVE_ROUNDS; round += 1) {
        const foot = plane.lengths["foreground-top"] ?? height;
        if (Math.abs(foot - wanted) < PLANE_TOLERANCE) {
            return { converged: true, plane };
        }
        height += wanted - foot;
        plane = planeGeometry(
            input,
            { height, width },
            { beside, cap, coreLift, faceFloor, ow, spare, topGap },
        );
    }
    return { converged: false, plane };
}

/**
 * The tilted table at `at.tilt`: the board laid out on a plane box so much deeper that, with the camera's foot on the
 * own row's top, the plane's top shows at the board's top.
 */
function viewWithin(input: BoardInput, screen: BoardGeometry, at: PlaneAt): TableView {
    const { width } = screen.box;
    const tableHeight = screen.lengths["table-h"] ?? screen.box.height;
    const footShown = screen.lengths["foreground-top"] ?? tableHeight;
    const lens = { distance: CAMERA_WIDTHS * width, tilt: at.tilt };
    const margin = at.margin ?? 0;
    const wanted = laidRise(lens, footShown - margin);
    const { converged, plane } = settlePlane(
        planeTarget(input, screen, { ...at, wanted }),
        wanted + tableHeight - footShown + margin,
    );
    const camera = {
        ...lens,
        pivot: { left: width / 2, top: footShown },
        planePivot: { left: plane.box.width / 2, top: plane.lengths["foreground-top"] ?? wanted },
    };
    const pieces = tablePieces(plane);
    return {
        camera,
        converged,
        flatCounters: screen.family === "phone" ? countersPlace(screen) : null,
        margin,
        pieces,
        ...laidTable(camera, { phone: screen.family === "phone", pieces, plane, screen }),
        tableTop: screen.lengths["table-top"] ?? 0,
        topGap: at.topGap ?? 0,
    };
}

function planeTarget(
    input: BoardInput,
    screen: BoardGeometry,
    at: PlaneAt & { readonly wanted: number },
): PlaneTarget {
    return {
        ...at,
        beside: screen.family === "phone" ? stripsBesideOwnRow(screen) : undefined,
        input,
        ow: at.ow ?? screen.lengths["ow"] ?? 1,
        spare: PLANE_SPARE,
        width: screen.box.width,
    };
}

/** Whether a phone's side strips run on beside its own row, as the flat board lays them. */
function stripsBesideOwnRow(screen: BoardGeometry): boolean {
    const own = screen.areas.hand;
    const strip = screen.areas["strip-left"];
    return own !== undefined && strip !== undefined && strip.bottom > own.top;
}

function countersPlace(screen: BoardGeometry): PlanePoint {
    return { left: screen.lengths["counters-x"] ?? 0, top: screen.lengths["counters-top"] ?? 0 };
}

function shownPiece(view: TableView, piece: TablePiece): BoardRect {
    const box = view.pieces[piece];
    if (piece === "dora" && view.flatCounters !== null) {
        const { left, top } = view.flatCounters;
        return {
            bottom: top + box.bottom - box.top,
            left,
            right: left + box.right - box.left,
            top,
        };
    }
    return shownRect(view.camera, box, view.shifts[piece]);
}

function middleOf(piece: BoardRect): number {
    return (piece.top + piece.bottom) / 2;
}

/** The river tile as the camera shows it across the core's middle. */
function apparentRiver(view: TableView): number {
    const rw = view.plane.lengths["rw"] ?? 0;
    return rw * scalesAt(view.camera, middleOf(view.pieces.centre)).across;
}

/** The nearest river tile's width as the camera shows it: the bottom river's near row. */
function nearRiver(view: TableView): number {
    const rw = view.plane.lengths["rw"] ?? 0;
    return rw * scalesAt(view.camera, view.pieces["river-bottom"].bottom).across;
}

/** The least face an opponent's strip may lay: its melds close their gaps down to the strips' face floor. */
function stripFace(plane: BoardGeometry): number {
    return plane.strips?.floor ?? Math.min(FACE_FLOOR, plane.lengths["rw"] ?? 0);
}

/** A face of width `width` at the plane's `top` as the camera shows it, by how its piece's tiles lie. */
function shownFace(
    camera: TableCamera,
    {
        facing,
        top,
        width,
    }: { readonly facing: PieceFacing; readonly top: number; readonly width: number },
): { readonly short: number; readonly long: number } {
    const { across, down } = scalesAt(camera, top);
    const height = width * TILE_ASPECT;
    const [wide, tall] =
        facing === "along" ? [width * across, height * down] : [height * across, width * down];
    return { long: Math.max(wide, tall), short: Math.min(wide, tall) };
}

const FAR_FACES = [
    "river-top",
    "river-left",
    "river-right",
    "strip-top",
    "strip-left",
    "strip-right",
] as const;

/** The smallest face the camera shows on the table: each far piece's farthest face. */
function farthestFace(view: TableView): { readonly short: number; readonly long: number } {
    const at = lengthOf(view.plane);
    const faces = FAR_FACES.map((piece) =>
        shownFace(view.camera, {
            facing: FACINGS[piece],
            top: view.pieces[piece].top,
            width: piece.startsWith("strip") ? stripFace(view.plane) : at("rw"),
        }),
    );
    return {
        long: Math.min(...faces.map(({ long }) => long)),
        short: Math.min(...faces.map(({ short }) => short)),
    };
}

/** The felt bands the camera shows: the top strip to the top river, the core to the own row's top. */
function shownBands(view: TableView): { readonly top: number; readonly bottom: number } {
    const ownRowTop = view.camera.pivot.top;
    const coreFoot = Math.max(
        shownPiece(view, "river-bottom").bottom,
        shownPiece(view, "river-left").bottom,
        shownPiece(view, "river-right").bottom,
    );
    const strip = view.pieces["strip-top"];
    const handFoot = projectPoint(view.camera, {
        left: (strip.left + strip.right) / 2,
        top: strip.top + uprightFoot(view.plane),
    }).top;
    return {
        bottom: ownRowTop - coreFoot,
        top: shownPiece(view, "river-top").top - handFoot,
    };
}

/** How deep an upright tile of the top strip lies from the strip's top, its edge under it: the hand's drawn foot. */
function uprightFoot(geometry: BoardGeometry): number {
    return (UPRIGHT_DEPTH + TILE_EDGE_SHARE) * (geometry.lengths["rw"] ?? 0);
}

/** The flat board's same bands. */
function flatBands(screen: BoardGeometry): { readonly top: number; readonly bottom: number } {
    const pieces = tablePieces(screen);
    const coreFoot = Math.max(
        pieces["river-bottom"].bottom,
        pieces["river-left"].bottom,
        pieces["river-right"].bottom,
    );
    return {
        bottom: (screen.lengths["foreground-top"] ?? coreFoot) - coreFoot,
        top: pieces["river-top"].top - pieces["strip-top"].top - uprightFoot(screen),
    };
}

/**
 * Where a side strip's inner edge shows at the board's `top`, if the strip reaches down that far: the camera turns its
 * edge, so its box's inner side (its far end's) says nothing of where it stands beside the own row.
 */
function innerEdgeAt(view: TableView, seat: SideStrip, top: number): number | null {
    const piece = view.pieces[seat];
    const shift = view.shifts[seat];
    const { camera } = view;
    const rise = laidRise(camera, camera.pivot.top - top);
    const planeTop = camera.planePivot.top - rise;
    if (planeTop > piece.bottom + shift.top) {
        return null;
    }
    const edge = seat === "strip-left" ? piece.right : piece.left;
    return projectPoint(camera, { left: edge + shift.left, top: planeTop }).left;
}

/**
 * Whether a desktop's side strips' farthest tiles show their wanted gap off the top strip's end tiles, and its counters
 * theirs off its first tile, whole on the board.
 */
function stripsClearTop(view: TableView, screen: BoardGeometry): boolean {
    if (screen.family === "phone") {
        return true;
    }
    const counters = shownPiece(view, "dora");
    return (
        (["strip-left", "strip-right"] as const).every(
            (seat) => sideTopGap(view, seat) >= sideTopWanted(screen, seat) - 0.5,
        ) &&
        stripEndFoot(view, "strip-left").left - counters.right >=
            countersWanted(view.pieces, screen) - 0.5 &&
        counters.left >= -0.5
    );
}

/** Whether both side strips show clear of the own row beside them (a phone's strips run on beside it). */
function sidesClearOwnRow(view: TableView, screen: BoardGeometry): boolean {
    const own = screen.areas.hand;
    if (own === undefined) {
        return true;
    }
    const left = innerEdgeAt(view, "strip-left", own.top);
    const right = innerEdgeAt(view, "strip-right", own.top);
    return (left === null || left <= own.left) && (right === null || right >= own.right);
}

/** A piece's near edge as the camera shows it: its lowest line on the screen, from its two near corners. */
function nearEdge(view: TableView, piece: TablePiece): BoardRect {
    const { bottom, left, right } = view.pieces[piece];
    const shift = view.shifts[piece];
    const [start, end] = [left, right].map((edge) =>
        projectPoint(view.camera, { left: edge + shift.left, top: bottom + shift.top }),
    );
    return {
        bottom: start?.top ?? 0,
        left: start?.left ?? 0,
        right: end?.left ?? 0,
        top: start?.top ?? 0,
    };
}

/**
 * Whether a phone's centre and side rivers show clear of its decisions' band by its least gap, where the flat board
 * keeps them clear: the band starts just under the centre, beside the right river's first tiles.
 */
function coreClearOfBand(view: TableView, screen: BoardGeometry): boolean {
    const band = screen.areas.actions;
    if (band === undefined || screen.family !== "phone") {
        return true;
    }
    const flat = tablePieces(screen);
    return (["centre", "river-left", "river-right"] as const).every(
        (piece) =>
            meets(flat[piece], band, BAND_CLEAR) || !meets(nearEdge(view, piece), band, BAND_CLEAR),
    );
}

function meets(first: BoardRect, second: BoardRect, gap: number): boolean {
    return (
        first.left < second.right + gap &&
        second.left < first.right + gap &&
        first.top < second.bottom + gap &&
        second.top < first.bottom + gap
    );
}

/**
 * How much narrower the top band may show than the flat board's: a pixel, or on a desktop a tenth of a river tile, so a
 * short desktop whose flat board opens a deep top band keeps a tilt step rather than going flat.
 */
function topBandSlack(screen: BoardGeometry): number {
    const rw = screen.lengths["rw"] ?? 0;
    return screen.family === "phone"
        ? BAND_SLACK
        : Math.max(BAND_SLACK, TOP_BAND_SLACK_RIVERS * rw);
}

/** A tilted board stands whole on its tiles' floors and keeps the flat board's bands within their allowance. */
function holds(view: TableView, screen: BoardGeometry): boolean {
    const flatRiver = screen.lengths["rw"] ?? 0;
    const face = farthestFace(view);
    const floor = Math.min(FACE_FLOOR, flatRiver);
    const shown = shownBands(view);
    const flat = flatBands(screen);
    const band = BAND_RIVERS * flatRiver;
    return (
        view.converged &&
        sidesClearOwnRow(view, screen) &&
        stripsClearTop(view, screen) &&
        coreClearOfBand(view, screen) &&
        (screen.family !== "phone" || shownMeldClear(view) >= flatMeldClear(screen) - BAND_SLACK) &&
        (view.plane.lengths["rw"] ?? 0) >= flatRiver - 1 &&
        Math.abs(apparentRiver(view) - flatRiver) <= APPARENT_RIVER_SHARE * flatRiver + 0.5 &&
        shown.top <= Math.max(flat.top, 0) + band + MARGIN_TOLERANCE &&
        shown.top >= flat.top - topBandSlack(screen) &&
        shown.bottom >= Math.min(flat.bottom, BOTTOM_BAND_LEAST) - 0.5 &&
        shown.bottom <= Math.max(flat.bottom, 0) + band + MARGIN_TOLERANCE &&
        nearRiver(view) <= NEAR_RIVER_BY_OWN * (screen.lengths["ow"] ?? 0) + 0.5 &&
        view.margin <= MARGIN_RIVERS * flatRiver + MARGIN_TOLERANCE &&
        face.short >= floor - 0.01 &&
        face.long >= floor * TILE_ASPECT - 0.01
    );
}

function laidFloor(shown: number, scale: number): number {
    return Math.ceil(shown / scale - 0.001);
}

/** How much the camera squashes the farthest river row down the screen. */
function farthestRiverDown(view: TableView): number {
    return Math.min(
        ...(["river-top", "river-left", "river-right"] as const).map(
            (piece) => scalesAt(view.camera, view.pieces[piece].top).down,
        ),
    );
}

/** How much higher the plane's centre must end for its near edges to show clear of the flat decisions' band. */
function coreLiftWanted(view: TableView, screen: BoardGeometry, already: number): number {
    const band = screen.areas.actions;
    if (band === undefined) {
        return already;
    }
    const flat = tablePieces(screen);
    const near = (["centre", "river-left", "river-right"] as const)
        .filter((piece) => !meets(flat[piece], band, BAND_CLEAR))
        .map((piece) => nearEdge(view, piece))
        .filter(
            (edge) => edge.left < band.right + BAND_CLEAR && band.left < edge.right + BAND_CLEAR,
        );
    const lowest = Math.max(-Infinity, ...near.map(({ bottom }) => bottom));
    const over = Math.max(0, lowest - (band.top - BAND_CLEAR));
    const { down } = scalesAt(view.camera, view.pieces.centre.bottom);
    return Math.max(already, Math.ceil(already + over / down));
}

/** Where the top strip's deepest meld can lie: the strip's top, its meld room's depth and its meld floor (px). */
interface MeldRoom {
    readonly geometry: BoardGeometry;
    readonly topGap: number;
    readonly floor: number;
}

/**
 * How low the top strip's deepest meld (an added kan's stack) can draw its foot, its edge under it: its tile at most a
 * river tile, within its meld room (which a phone's plane keeps above the felt it widens under the strip), never under
 * the meld floor.
 */
function meldRoomFoot({ floor, geometry, topGap }: MeldRoom): number {
    const { top } = tablePieces(geometry)["strip-top"];
    const room = (geometry.lengths["core-top"] ?? 0) - TOP_CORE_CLEAR - topGap - top;
    const tile = Math.max(floor, Math.min(geometry.lengths["rw"] ?? 0, room / STACKED_DEPTH));
    return top + (STACKED_DEPTH + TILE_EDGE_SHARE) * tile;
}

/** The felt the flat board keeps between the top strip's meld room and the top river (px). */
function flatMeldClear(screen: BoardGeometry): number {
    return (
        tablePieces(screen)["river-top"].top -
        meldRoomFoot({ floor: FACE_FLOOR, geometry: screen, topGap: 0 })
    );
}

/** The same felt as the camera shows it (px). */
function shownMeldClear(view: TableView): number {
    const strip = view.pieces["strip-top"];
    const foot = projectPoint(view.camera, {
        left: (strip.left + strip.right) / 2,
        top: meldRoomFoot({
            floor: stripFaceFloor(view),
            geometry: view.plane,
            topGap: view.topGap,
        }),
    });
    return shownPiece(view, "river-top").top - foot.top;
}

/**
 * How much the plane's gap under the top strip must widen for the camera to show the flat board's, under both the hand's
 * foot and the meld room's (the gap widens the felt under the room, not the room).
 */
function topGapWanted(view: TableView, screen: BoardGeometry, already: number): number {
    const handFoot = view.pieces["strip-top"].top + uprightFoot(view.plane);
    const laidGap = view.pieces["river-top"].top - handFoot;
    const roomFoot = meldRoomFoot({
        floor: stripFaceFloor(view),
        geometry: view.plane,
        topGap: view.topGap,
    });
    const laidClear = view.pieces["river-top"].top - roomFoot;
    const handDown = scalesAt(view.camera, handFoot).down;
    const roomDown = scalesAt(view.camera, roomFoot).down;
    const wider = Math.max(
        flatBands(screen).top / handDown - laidGap,
        flatMeldClear(screen) / roomDown - laidClear,
    );
    return Math.max(already, Math.ceil(already + wider));
}

/**
 * A phone's view at `tilt`, its plane laying its tiles so much larger that, after the camera's foreshortening, its
 * farthest faces still show at the face floor: the river tile, the strips' meld floor and its gaps raised by rounds
 * until a round asks for what the last one did, else marked unsettled.
 */
function phoneViewAt(input: BoardInput, screen: BoardGeometry, tilt: number): TableView {
    const flatRiver = screen.lengths["rw"] ?? 1;
    let view = viewWithin(input, screen, { cap: flatRiver, tilt });
    let at: PlaneAt = { cap: flatRiver, coreLift: 0, tilt, topGap: 0 };
    for (let round = 0; round < PHONE_FLOOR_ROUNDS; round += 1) {
        const next = {
            cap: Math.max(flatRiver, laidFloor(FACE_FLOOR, farthestRiverDown(view))),
            coreLift: coreLiftWanted(view, screen, at.coreLift ?? 0),
            faceFloor: stripFaceFloor(view),
            tilt,
            topGap: topGapWanted(view, screen, at.topGap ?? 0),
        };
        if (round > 0 && samePlaneAt(next, at)) {
            return view;
        }
        at = next;
        view = narrowedOwnRow(input, screen, at);
    }
    return { ...view, converged: false };
}

/** Whether two rounds ask the plane for the same tiles and gaps: the phone's rounds have settled. */
function samePlaneAt(first: PlaneAt, second: PlaneAt): boolean {
    return (
        first.cap === second.cap &&
        first.coreLift === second.coreLift &&
        first.faceFloor === second.faceFloor &&
        first.topGap === second.topGap
    );
}

/**
 * The plane at `at`, its undrawn own row laid narrower, a pixel at a time down to `PLANE_OWN_LEAST` of the flat own tile,
 * where the flat one's width leaves the bars too little room for the larger laid tiles' river tile.
 */
function narrowedOwnRow(input: BoardInput, screen: BoardGeometry, at: PlaneAt): TableView {
    const flatRiver = screen.lengths["rw"] ?? 1;
    const flatOwn = screen.lengths["ow"] ?? 1;
    let view = viewWithin(input, screen, at);
    for (
        let ow = flatOwn - 1;
        ow >= Math.ceil(PLANE_OWN_LEAST * flatOwn) && (view.plane.lengths["rw"] ?? 0) < flatRiver;
        ow -= 1
    ) {
        view = viewWithin(input, screen, { ...at, ow });
    }
    return view;
}

/**
 * A desktop's view at `tilt`: its laid river tile as large as shows across the core's middle within 5% of the flat
 * board's, a few steps down from the largest the plane holds.
 */
function desktopViewAt(input: BoardInput, screen: BoardGeometry, tilt: number): TableView {
    const capped = cappedView(input, screen, tilt);
    const at = { cap: capped.plane.lengths["rw"] ?? 1, faceFloor: stripFaceFloor(capped), tilt };
    return marginedView(input, screen, at);
}

/**
 * The view at `at` with the least top margin (to `MARGIN_RIVERS` river tiles) whose bands hold their allowance, found by halving:
 * a wider margin leaves the plane shorter and its bands narrower. Where even the widest leaves them over, that one.
 */
function marginedView(input: BoardInput, screen: BoardGeometry, at: PlaneAt): TableView {
    const unmargined = viewWithin(input, screen, at);
    if (bandOverflow(unmargined, screen) <= MARGIN_TOLERANCE) {
        return unmargined;
    }
    const widest = viewWithin(input, screen, {
        ...at,
        margin: MARGIN_RIVERS * (screen.lengths["rw"] ?? 0),
    });
    if (bandOverflow(widest, screen) > MARGIN_TOLERANCE) {
        return widest;
    }
    return halvedMargin(input, screen, { at, held: widest });
}

/** The least margin whose bands hold, halving between none (which does not) and `held`'s (which does). */
function halvedMargin(
    input: BoardInput,
    screen: BoardGeometry,
    { at, held }: { readonly at: PlaneAt; readonly held: TableView },
): TableView {
    let low = 0;
    let view = held;
    while (view.margin - low > MARGIN_TOLERANCE) {
        const margin = (low + view.margin) / 2;
        const trial = viewWithin(input, screen, { ...at, margin });
        if (bandOverflow(trial, screen) > MARGIN_TOLERANCE) {
            low = margin;
        } else {
            view = trial;
        }
    }
    return view;
}

/** A desktop's view at `tilt` whose laid river tile keeps the middle river's 5% band and the nearest's lead under the own. */
function cappedView(input: BoardInput, screen: BoardGeometry, tilt: number): TableView {
    const flatRiver = screen.lengths["rw"] ?? 1;
    const caps = {
        most: (1 + APPARENT_RIVER_SHARE) * flatRiver,
        nearest: NEAR_RIVER_BY_OWN * (screen.lengths["ow"] ?? flatRiver),
    };
    let view = viewWithin(input, screen, { cap: 2 * flatRiver, tilt });
    for (let step = 0; step < CAP_STEPS && !withinCaps(view, caps); step += 1) {
        const middle = scalesAt(view.camera, middleOf(view.pieces.centre)).across;
        const near = scalesAt(view.camera, view.pieces["river-bottom"].bottom).across;
        const cap = Math.min(
            (view.plane.lengths["rw"] ?? 1) - 1,
            Math.floor(caps.most / middle),
            Math.floor(caps.nearest / near),
        );
        view = viewWithin(input, screen, { cap, faceFloor: stripFaceFloor(view), tilt });
    }
    return withinCaps(view, caps) ? view : { ...view, converged: false };
}

/** How much felt the bands show beyond their allowance, which the table's top margin takes instead (px). */
function bandOverflow(view: TableView, screen: BoardGeometry): number {
    const shown = shownBands(view);
    const flat = flatBands(screen);
    const band = BAND_RIVERS * (screen.lengths["rw"] ?? 0);
    return (
        Math.max(0, shown.top - Math.max(flat.top, 0) - band) +
        Math.max(0, shown.bottom - Math.max(flat.bottom, 0) - band)
    );
}

function withinCaps(
    view: TableView,
    { most, nearest }: Readonly<Record<"most" | "nearest", number>>,
): boolean {
    return apparentRiver(view) <= most && nearRiver(view) <= nearest + 0.5;
}

/**
 * The strips' laid meld floor that shows their farthest faces a pixel over the face floor under `view`'s camera: a face
 * the camera resamples softens its thinnest strokes, which a flat face at the floor keeps crisp.
 */
function stripFaceFloor(view: TableView): number {
    const down = Math.min(
        ...(["strip-top", "strip-left", "strip-right"] as const).map(
            (piece) => scalesAt(view.camera, view.pieces[piece].top).down,
        ),
    );
    return laidFloor(FACE_FLOOR + TILTED_FACE_MARGIN, down);
}

function viewAt(input: BoardInput, screen: BoardGeometry, tilt: number): TableView {
    return screen.family === "phone"
        ? phoneViewAt(input, screen, tilt)
        : desktopViewAt(input, screen, tilt);
}

/** The flat board as a view: no tilt, the plane the board's own geometry. */
function flatView(screen: BoardGeometry): TableView {
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

/**
 * The table as the camera shows it: the steepest tilt (20 degrees at most on a desktop, 15 on a phone, 10 at least)
 * whose plane settles, keeps the farthest faces at the face floor, keeps the nearest river tile under the own tile and
 * keeps its felt bands near the flat board's; else the flat board.
 */
function tableView(input: BoardInput, screen: BoardGeometry): TableView {
    if (screen.family === "phone" && (screen.lengths["rw"] ?? 0) <= FACE_FLOOR) {
        return flatView(screen);
    }
    const tilts = screen.family === "phone" ? PHONE_TILTS : DESKTOP_TILTS;
    for (const tilt of tilts) {
        const view = viewAt(input, screen, tilt);
        if (holds(view, screen)) {
            return view;
        }
    }
    return flatView(screen);
}

function showPlanePoint(view: TableView, point: PlanePoint): PlanePoint {
    return projectPoint(view.camera, point);
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

/** A piece's homography from its own box onto the surface: its move on the plane, the camera, back to its box. */
function pieceMatrix(view: TableView, piece: TablePiece): Matrix3 {
    const box = view.pieces[piece];
    const shift = view.shifts[piece];
    const into = translation({ left: box.left + shift.left, top: box.top + shift.top });
    const back = translation({ left: -box.left, top: view.tableTop - box.top });
    return multiply(back, multiply(homography(view.camera), into));
}

/**
 * A piece's CSS `matrix3d`, from its own box's top left corner on the surface (which stands the flat table's top above
 * the layout) to where the camera shows it: the piece's move on the plane, then the camera's homography.
 */
function pieceTransform(view: TableView, piece: TablePiece): string {
    const box = view.pieces[piece];
    if (piece === "dora" && view.flatCounters !== null) {
        const { left, top } = view.flatCounters;
        return `translate(${px(left - box.left)}, ${px(top + view.tableTop - box.top)})`;
    }
    const [across, down, weight] = pieceMatrix(view, piece);
    const scale = weight.at(-1) ?? 1;
    const values = [
        across[0] / scale,
        down[0] / scale,
        0,
        weight[0] / scale,
        across[1] / scale,
        down[1] / scale,
        0,
        weight[1] / scale,
        0,
        0,
        1,
        0,
        across[2] / scale,
        down[2] / scale,
        0,
        1,
    ];
    return `matrix3d(${values.join(", ")})`;
}

const SCREEN_ONLY_LENGTHS = new Set(["table-h", "table-top"]);

/**
 * A plate's top left (or top right) corner on the layout: its flat box standing on its tilted anchor; a top row plate
 * raised further where its riichi stick, hanging under its pill (which the box centres), would come nearer a river or
 * the centre under it than the stick's least gap.
 */
function platePlace(view: TableView, screen: BoardGeometry, seat: SeatPosition): PlanePoint {
    const shown = showPlanePoint(view, plateAnchor(view.plane, seat));
    if (!topRowPlate(seat)) {
        return { left: shown.left, top: shown.top };
    }
    const top = shown.top - (screen.lengths["badge-h"] ?? 0);
    const stick = stickUnder(screen, { left: shown.left, seat, top });
    const nearest = Math.min(
        Infinity,
        ...(["centre", "river-left", "river-right", "river-top"] as const)
            .map((piece) => shownPiece(view, piece))
            .filter(
                (piece) =>
                    piece.left < stick.right &&
                    stick.left < piece.right &&
                    piece.bottom > stick.foot - 1,
            )
            .map((piece) => piece.top),
    );
    const least = screen.family === "phone" ? PHONE_STICK_GAP : STICK_GAP;
    return { left: shown.left, top: top - Math.max(0, stick.foot + least - nearest) };
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
            pillTop + at("pill-h") + STICK_DROP + STICK_LENGTH_BY_TEXT * at("text") * STICK_ASPECT,
        left: reachesLeft ? left - at("plate-w") : left,
        right: reachesLeft ? left : left + at("plate-w"),
    };
}

/** What the board takes from the camera: the flat table's place and the flat overlays' tilted anchors. */
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
            pointValues(`--geo-shown-centre-${corner}`, showPlanePoint(view, point)),
        ),
        ...SEAT_POSITIONS.flatMap((seat) =>
            pointValues(
                `--geo-shown-callout-${seat}`,
                showPlanePoint(view, calloutSpot(view.plane, seat)),
            ),
        ),
        ...SEAT_POSITIONS.flatMap((seat) =>
            pointValues(`--geo-shown-plate-${seat}`, platePlace(view, screen, seat)),
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
            pieceTransform(view, piece),
        ]),
    ];
}

export {
    TABLE_PIECES,
    apparentRiver,
    boardViewValues,
    farthestFace,
    flatBands,
    nearRiver,
    pieceTransform,
    platePlace,
    projectPoint,
    stickUnder,
    scalesAt,
    showPlanePoint,
    shownBands,
    shownPiece,
    surfaceViewValues,
    tablePieces,
    tableView,
    viewAt,
};
export type { PlanePoint, TableCamera, TablePiece, TableView };
