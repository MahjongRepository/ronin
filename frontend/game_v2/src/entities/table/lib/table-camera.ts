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

const DESKTOP_TILTS = [25, 22, 20, 18, 15, 12, 9, 6, 3] as const;
const PHONE_TILTS = [15, 12, 9, 6, 3] as const;

const CAMERA_WIDTHS = 2;

/** The river tile across the tilted core's middle shows within this share of the flat board's. */
const APPARENT_RIVER_SHARE = 0.05;

/** The nearest river tile shows at most this share of the own tile, so the own hand stays the table's largest. */
const NEAR_RIVER_BY_OWN = 0.85;

/** A felt band between the table's pieces may open at most this many flat river tiles wider than the flat board's. */
const BAND_RIVERS = 0.75;

const CAP_STEPS = 4;

const PLANE_SPARE: PlaneSpare = "around-core";
const PHONE_FLOOR_ROUNDS = 3;

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
    /** What each piece moves by on the screen after the camera, to keep a side strip inside its flat place. */
    readonly shifts: Readonly<Record<TablePiece, PlanePoint>>;
    /** The flat table's top on the board, where the tilted table's top shows too. */
    readonly tableTop: number;
    readonly converged: boolean;
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
        corners(piece).map((corner) => {
            const shown = projectPoint(camera, corner);
            return { left: shown.left + shift.left, top: shown.top + shift.top };
        }),
    );
}

/** How far a side strip moves in to keep its outer edge no farther out than the flat board's. */
function outerFit(flat: BoardRect | undefined, seat: SideStrip, shown: BoardRect): number {
    if (flat === undefined) {
        return 0;
    }
    return seat === "strip-left"
        ? Math.max(0, flat.left - shown.left)
        : Math.min(0, flat.right - shown.right);
}

/**
 * A side strip's screen shift: its outer edge no farther out than the flat board's, and on a desktop its near end above
 * the own row's top (a phone's strips run on beside the own row).
 */
function sideShift(
    camera: TableCamera,
    { phone, screen }: { readonly screen: BoardGeometry; readonly phone: boolean },
    { piece, seat }: { readonly piece: BoardRect; readonly seat: SideStrip },
): PlanePoint {
    const shown = shownRect(camera, piece, { left: 0, top: 0 });
    const ownRowTop = screen.lengths["foreground-top"] ?? shown.bottom;
    return {
        left: outerFit(screen.areas[seat], seat, shown),
        top: phone ? 0 : Math.min(0, ownRowTop - shown.bottom),
    };
}

function tableShifts(
    camera: TableCamera,
    {
        phone,
        pieces,
        screen,
    }: { phone: boolean; pieces: Record<TablePiece, BoardRect>; screen: BoardGeometry },
): Record<TablePiece, PlanePoint> {
    const still = { left: 0, top: 0 };
    function side(seat: SideStrip): PlanePoint {
        return sideShift(camera, { phone, screen }, { piece: pieces[seat], seat });
    }
    return {
        centre: still,
        dora: still,
        "river-bottom": still,
        "river-left": still,
        "river-right": still,
        "river-top": still,
        "strip-left": side("strip-left"),
        "strip-right": side("strip-right"),
        "strip-top": still,
    };
}

interface PlaneAt {
    readonly cap: number;
    readonly tilt: number;
    readonly faceFloor?: number;
    readonly topGap?: number;
}

interface PlaneTarget extends PlaneAt {
    readonly input: BoardInput;
    readonly width: number;
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
    const { cap, faceFloor, input, ow, spare, topGap, wanted, width } = target;
    let height = start;
    let plane = planeGeometry(input, { height, width }, { cap, faceFloor, ow, spare, topGap });
    for (let round = 0; round < PLANE_SOLVE_ROUNDS; round += 1) {
        const foot = plane.lengths["foreground-top"] ?? height;
        if (Math.abs(foot - wanted) < PLANE_TOLERANCE) {
            return { converged: true, plane };
        }
        height += wanted - foot;
        plane = planeGeometry(input, { height, width }, { cap, faceFloor, ow, spare, topGap });
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
    const wanted = laidRise(lens, footShown);
    const target = {
        ...at,
        input,
        ow: screen.lengths["ow"] ?? 1,
        spare: PLANE_SPARE,
        wanted,
        width,
    };
    const { converged, plane } = settlePlane(target, wanted + tableHeight - footShown);
    const camera = {
        ...lens,
        pivot: { left: width / 2, top: footShown },
        planePivot: { left: plane.box.width / 2, top: plane.lengths["foreground-top"] ?? wanted },
    };
    const pieces = tablePieces(plane);
    return {
        camera,
        converged,
        pieces,
        plane,
        shifts: tableShifts(camera, { phone: screen.family === "phone", pieces, screen }),
        tableTop: screen.lengths["table-top"] ?? 0,
    };
}

function shownPiece(view: TableView, piece: TablePiece): BoardRect {
    return shownRect(view.camera, view.pieces[piece], view.shifts[piece]);
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
    return {
        bottom: ownRowTop - coreFoot,
        top: shownPiece(view, "river-top").top - shownPiece(view, "strip-top").bottom,
    };
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
        top: pieces["river-top"].top - pieces["strip-top"].bottom,
    };
}

/** Whether both side strips show clear of the own row beside them (a phone's strips run on beside it). */
function sidesClearOwnRow(view: TableView, screen: BoardGeometry): boolean {
    const own = screen.areas.hand;
    if (own === undefined) {
        return true;
    }
    const left = shownPiece(view, "strip-left");
    const right = shownPiece(view, "strip-right");
    const { left: ownLeft, right: ownRight, top: ownTop } = own;
    return (
        (left.bottom <= ownTop || left.right <= ownLeft) &&
        (right.bottom <= ownTop || right.left >= ownRight)
    );
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
        (view.plane.lengths["rw"] ?? 0) >= flatRiver &&
        shown.top <= Math.max(flat.top, 0) + band &&
        shown.top >= flat.top - 0.5 &&
        shown.bottom >= flat.bottom - 0.5 &&
        shown.bottom <= Math.max(flat.bottom, 0) + band &&
        nearRiver(view) <= NEAR_RIVER_BY_OWN * (screen.lengths["ow"] ?? 0) + 0.5 &&
        face.short >= floor - 0.01 &&
        face.long >= floor * TILE_ASPECT - 0.01
    );
}

function laidFloor(shown: number, scale: number): number {
    return Math.ceil(shown / scale - 0.001);
}

/**
 * A phone's view at `tilt`, its plane laying its tiles so much larger that, after the camera's foreshortening, its
 * farthest faces still show at the face floor: the river tile and the strips' meld floor raised by rounds.
 */
function farthestRiverDown(view: TableView): number {
    return Math.min(
        ...(["river-top", "river-left", "river-right"] as const).map(
            (piece) => scalesAt(view.camera, view.pieces[piece].top).down,
        ),
    );
}

/** How much the plane's gap under the top strip must widen for the camera to show the flat board's. */
function topGapWanted(view: TableView, screen: BoardGeometry, already: number): number {
    const laidGap = view.pieces["river-top"].top - view.pieces["strip-top"].bottom;
    const { down } = scalesAt(view.camera, view.pieces["strip-top"].bottom);
    return Math.max(already, Math.ceil(already + flatBands(screen).top / down - laidGap));
}

function phoneViewAt(input: BoardInput, screen: BoardGeometry, tilt: number): TableView {
    const flatRiver = screen.lengths["rw"] ?? 1;
    let view = viewWithin(input, screen, { cap: flatRiver, tilt });
    let topGap = 0;
    for (let round = 0; round < PHONE_FLOOR_ROUNDS; round += 1) {
        topGap = topGapWanted(view, screen, topGap);
        const cap = Math.max(flatRiver, laidFloor(FACE_FLOOR, farthestRiverDown(view)));
        view = viewWithin(input, screen, { cap, faceFloor: stripFaceFloor(view), tilt, topGap });
    }
    return view;
}

/**
 * A desktop's view at `tilt`: its laid river tile as large as shows across the core's middle within 5% of the flat
 * board's, a few steps down from the largest the plane holds.
 */
function desktopViewAt(input: BoardInput, screen: BoardGeometry, tilt: number): TableView {
    const flatRiver = screen.lengths["rw"] ?? 1;
    const most = (1 + APPARENT_RIVER_SHARE) * flatRiver;
    let view = viewWithin(input, screen, { cap: 2 * flatRiver, tilt });
    let faceFloor = stripFaceFloor(view);
    for (let step = 0; step < CAP_STEPS && apparentRiver(view) > most; step += 1) {
        const { across } = scalesAt(view.camera, middleOf(view.pieces.centre));
        const cap = Math.min((view.plane.lengths["rw"] ?? 1) - 1, Math.floor(most / across));
        view = viewWithin(input, screen, { cap, faceFloor, tilt });
        faceFloor = stripFaceFloor(view);
    }
    return viewWithin(input, screen, { cap: view.plane.lengths["rw"] ?? 1, faceFloor, tilt });
}

/** The strips' laid meld floor that shows their farthest faces at the face floor under `view`'s camera. */
function stripFaceFloor(view: TableView): number {
    const down = Math.min(
        ...(["strip-top", "strip-left", "strip-right"] as const).map(
            (piece) => scalesAt(view.camera, view.pieces[piece].top).down,
        ),
    );
    return laidFloor(FACE_FLOOR, down);
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
    const pieces = tablePieces(screen);
    const still = { left: 0, top: 0 };
    return {
        camera,
        converged: true,
        pieces,
        plane: screen,
        shifts: {
            centre: still,
            dora: still,
            "river-bottom": still,
            "river-left": still,
            "river-right": still,
            "river-top": still,
            "strip-left": still,
            "strip-right": still,
            "strip-top": still,
        },
        tableTop: screen.lengths["table-top"] ?? 0,
    };
}

/**
 * The table as the camera shows it: the steepest tilt (25 degrees at most on a desktop, 15 on a phone) whose plane
 * settles, keeps the farthest faces at the face floor, keeps the nearest river tile under the own tile and opens no
 * felt band much wider than the flat board's; else the flat board.
 */
function tableView(input: BoardInput, screen: BoardGeometry): TableView {
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

/** A plate's anchor: its inner edge at its box's middle, which the flat plate then stands centred on. */
function plateAnchor(plane: BoardGeometry, seat: SeatPosition): PlanePoint {
    const at = lengthOf(plane);
    const inner = plane.box.width - at("plate-left-right");
    const middle = at("badge-h") / 2;
    const anchors: Readonly<Record<SeatPosition, PlanePoint>> = {
        bottom: { left: at("plate-right-left"), top: at("plate-bottom-top") + middle },
        left: { left: inner, top: at("plate-bottom-top") + middle },
        right: { left: at("plate-right-left"), top: at("plate-top-top") + middle },
        top: { left: inner, top: at("plate-top-top") + middle },
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

/**
 * A piece's CSS `matrix3d`, from its own box's top left corner on the surface (which stands at the board's top, the
 * layout `surfaceTop` above it) to where the camera shows it: the camera's homography, then the piece's screen shift.
 */
function pieceTransform(view: TableView, piece: TablePiece): string {
    const box = view.pieces[piece];
    const shift = view.shifts[piece];
    const into = translation({ left: box.left, top: box.top });
    const back = translation({
        left: shift.left - box.left,
        top: shift.top + view.tableTop - box.top,
    });
    const [across, down, weight] = multiply(back, multiply(homography(view.camera), into));
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
    projectPoint,
    scalesAt,
    showPlanePoint,
    shownBands,
    shownPiece,
    surfaceViewValues,
    tableView,
};
export type { PlanePoint, TableCamera, TablePiece, TableView };
