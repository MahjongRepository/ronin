import { SEAT_POSITIONS, type SeatPosition } from "@/entities/table/model/board-types";

import { type BoardGeometry, type BoardRect } from "./board-geometry";
import { CALLOUT_SPOTS } from "./callouts";

const DESKTOP_TILT_DEG = 25;
const PHONE_TILT_DEG = 15;

const CAMERA_WIDTHS = 2;

const TABLE_PIECES = ["core", "strip-top", "strip-right", "strip-left"] as const;

type TablePiece = (typeof TABLE_PIECES)[number];

interface PlanePoint {
    readonly left: number;
    readonly top: number;
}

interface TableCamera {
    readonly tilt: number;
    readonly distance: number;
    readonly pivot: PlanePoint;
}

interface PiecePose {
    readonly anchor: PlanePoint;
    readonly shift: PlanePoint;
    readonly scale: number;
}

interface TableView {
    readonly camera: TableCamera;
    readonly pieces: Readonly<Record<TablePiece, BoardRect>>;
    readonly poses: Readonly<Record<TablePiece, PiecePose>>;
}

function tableCamera(geometry: BoardGeometry): TableCamera {
    return {
        distance: CAMERA_WIDTHS * geometry.box.width,
        pivot: {
            left: geometry.lengths["cx"] ?? geometry.box.width / 2,
            top: geometry.lengths["table-h"] ?? geometry.box.height,
        },
        tilt: geometry.family === "phone" ? PHONE_TILT_DEG : DESKTOP_TILT_DEG,
    };
}

function radians({ tilt }: TableCamera): number {
    return (tilt * Math.PI) / 180;
}

function depthScale(camera: TableCamera, rise: number): number {
    return camera.distance / (camera.distance + rise * Math.sin(radians(camera)));
}

function projectPoint(camera: TableCamera, point: PlanePoint): PlanePoint {
    const rise = camera.pivot.top - point.top;
    const scale = depthScale(camera, rise);
    return {
        left: camera.pivot.left + (point.left - camera.pivot.left) * scale,
        top: camera.pivot.top - rise * Math.cos(radians(camera)) * scale,
    };
}

function unprojectPoint(camera: TableCamera, point: PlanePoint): PlanePoint {
    const angle = radians(camera);
    const shown = camera.pivot.top - point.top;
    const rise =
        (shown * camera.distance) / (Math.cos(angle) * camera.distance - shown * Math.sin(angle));
    return {
        left: camera.pivot.left + (point.left - camera.pivot.left) / depthScale(camera, rise),
        top: camera.pivot.top - rise,
    };
}

function union(rects: readonly BoardRect[]): BoardRect {
    return {
        bottom: Math.max(...rects.map(({ bottom }) => bottom)),
        left: Math.min(...rects.map(({ left }) => left)),
        right: Math.max(...rects.map(({ right }) => right)),
        top: Math.min(...rects.map(({ top }) => top)),
    };
}

function lengthOf(geometry: BoardGeometry): (name: string) => number {
    return function at(name: string): number {
        return geometry.lengths[name] ?? 0;
    };
}

function coreRect(geometry: BoardGeometry): BoardRect {
    const at = lengthOf(geometry);
    const [cx, cy, hx, h, gap] = [at("cx"), at("cy"), at("hx"), at("h"), at("g")];
    const along = at("river-along");
    const across = at("river-across");
    return union([
        { bottom: cy + h + gap + across, left: cx - hx, right: cx - hx + along, top: cy + h + gap },
        {
            bottom: cy - h + along,
            left: cx - hx - gap - across,
            right: cx - hx - gap,
            top: cy - h,
        },
        { bottom: cy + h, left: cx + hx + gap, right: cx + hx + gap + across, top: cy + h - along },
        {
            bottom: cy - h - at("g-top"),
            left: cx + hx - along,
            right: cx + hx,
            top: cy - h - at("g-top") - across,
        },
    ]);
}

function tablePieces(geometry: BoardGeometry): Record<TablePiece, BoardRect> {
    const none = coreRect(geometry);
    return {
        core: none,
        "strip-left": geometry.areas["strip-left"] ?? none,
        "strip-right": geometry.areas["strip-right"] ?? none,
        "strip-top": geometry.areas["strip-top"] ?? none,
    };
}

type PieceHold = "far-edge" | "middle";

const PIECE_HOLDS: Readonly<Record<TablePiece, PieceHold>> = {
    core: "middle",
    "strip-left": "middle",
    "strip-right": "middle",
    "strip-top": "far-edge",
};

function pieceAnchor(camera: TableCamera, piece: BoardRect, hold: PieceHold): PlanePoint {
    return {
        left: Math.min(piece.right, Math.max(piece.left, camera.pivot.left)),
        top: hold === "far-edge" ? piece.top : (piece.top + piece.bottom) / 2,
    };
}

function laidPoint({ anchor, scale, shift }: PiecePose, point: PlanePoint): PlanePoint {
    return {
        left: anchor.left + shift.left + scale * (point.left - anchor.left),
        top: anchor.top + shift.top + scale * (point.top - anchor.top),
    };
}

function shownCorners(camera: TableCamera, piece: BoardRect, pose: PiecePose): PlanePoint[] {
    return [
        { left: piece.left, top: piece.top },
        { left: piece.right, top: piece.top },
        { left: piece.left, top: piece.bottom },
        { left: piece.right, top: piece.bottom },
    ].map((corner) => projectPoint(camera, laidPoint(pose, corner)));
}

function outerOverhang(camera: TableCamera, piece: BoardRect, pose: PiecePose): number {
    if (piece.left < camera.pivot.left && camera.pivot.left < piece.right) {
        return 0;
    }
    const corners = shownCorners(camera, piece, pose);
    const nearest = laidPoint(pose, { left: piece.left, top: piece.bottom });
    const scale = depthScale(camera, camera.pivot.top - nearest.top);
    if ((piece.left + piece.right) / 2 < camera.pivot.left) {
        return Math.max(0, piece.left - Math.min(...corners.map(({ left }) => left))) / scale;
    }
    return -Math.max(0, Math.max(...corners.map(({ left }) => left)) - piece.right) / scale;
}

function liftedAbove(
    camera: TableCamera,
    { floor, piece }: { readonly floor: number; readonly piece: BoardRect },
    pose: PiecePose,
): PiecePose {
    const shownBottom = Math.max(...shownCorners(camera, piece, pose).map(({ top }) => top));
    if (shownBottom <= floor) {
        return pose;
    }
    const laidFloor = unprojectPoint(camera, { left: camera.pivot.left, top: floor }).top;
    const { anchor, scale } = pose;
    return {
        ...pose,
        shift: {
            left: pose.shift.left,
            top: laidFloor - anchor.top - scale * (piece.bottom - anchor.top),
        },
    };
}

function piecePose(
    camera: TableCamera,
    piece: BoardRect,
    { floor, hold }: { readonly floor: number; readonly hold: PieceHold },
): PiecePose {
    const anchor = pieceAnchor(camera, piece, hold);
    const laid = unprojectPoint(camera, anchor);
    const placed = liftedAbove(
        camera,
        { floor, piece },
        {
            anchor,
            scale: 1 / depthScale(camera, camera.pivot.top - laid.top),
            shift: { left: laid.left - anchor.left, top: laid.top - anchor.top },
        },
    );
    return {
        ...placed,
        shift: {
            left: placed.shift.left + outerOverhang(camera, piece, placed),
            top: placed.shift.top,
        },
    };
}

function tableView(geometry: BoardGeometry): TableView {
    const camera = tableCamera(geometry);
    const pieces = tablePieces(geometry);
    const floor = geometry.lengths["foreground-top"] ?? camera.pivot.top;
    function pose(piece: TablePiece): PiecePose {
        return piecePose(camera, pieces[piece], { floor, hold: PIECE_HOLDS[piece] });
    }
    return {
        camera,
        pieces,
        poses: {
            core: pose("core"),
            "strip-left": pose("strip-left"),
            "strip-right": pose("strip-right"),
            "strip-top": pose("strip-top"),
        },
    };
}

function showPiecePoint(view: TableView, piece: TablePiece, point: PlanePoint): PlanePoint {
    return projectPoint(view.camera, laidPoint(view.poses[piece], point));
}

function shownPiece(view: TableView, piece: TablePiece): BoardRect {
    const corners = shownCorners(view.camera, view.pieces[piece], view.poses[piece]);
    return union(corners.map(({ left, top }) => ({ bottom: top, left, right: left, top })));
}

function calloutSpot(geometry: BoardGeometry, seat: SeatPosition): PlanePoint {
    const at = lengthOf(geometry);
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

function plateAnchor(geometry: BoardGeometry, seat: SeatPosition): PlanePoint {
    const at = lengthOf(geometry);
    const inner = geometry.box.width - at("plate-left-right");
    const anchors: Readonly<Record<SeatPosition, PlanePoint>> = {
        bottom: { left: at("plate-right-left"), top: at("plate-bottom-top") },
        left: { left: inner, top: at("plate-bottom-top") },
        right: { left: at("plate-right-left"), top: at("plate-top-top") },
        top: { left: inner, top: at("plate-top-top") },
    };
    return anchors[seat];
}

function centreCorners(
    geometry: BoardGeometry,
): Readonly<Record<"bl" | "br" | "tl" | "tr", PlanePoint>> {
    const at = lengthOf(geometry);
    const left = at("cx") - at("hx");
    const top = at("cy") - at("h");
    return {
        bl: { left, top: top + at("c") },
        br: { left: left + at("w"), top: top + at("c") },
        tl: { left, top },
        tr: { left: left + at("w"), top },
    };
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

function poseValues(view: TableView, piece: TablePiece, origin: PlanePoint): [string, string][] {
    const { anchor, scale, shift } = view.poses[piece];
    return [
        ...pointValues(`--geo-plane-${piece}-shift`, shift),
        ...pointValues(`--geo-plane-${piece}-anchor`, {
            left: anchor.left - origin.left,
            top: anchor.top - origin.top,
        }),
        [`--geo-plane-${piece}-scale`, String(scale)],
    ];
}

function tableViewValues(geometry: BoardGeometry): [string, string][] {
    const view = tableView(geometry);
    const { camera } = view;
    return [
        ["--geo-plane-camera", px(camera.distance)],
        ["--geo-plane-tilt", `${camera.tilt}deg`],
        ...pointValues("--geo-plane-pivot", camera.pivot),
        ...pointValues("--geo-plane-core-start", {
            left: view.pieces.core.left,
            top: view.pieces.core.top,
        }),
        ...pointValues("--geo-plane-core-size", {
            left: view.pieces.core.right - view.pieces.core.left,
            top: view.pieces.core.bottom - view.pieces.core.top,
        }),
        ...TABLE_PIECES.flatMap((piece) =>
            poseValues(
                view,
                piece,
                piece === "core"
                    ? centreCorners(geometry).tl
                    : { left: view.pieces[piece].left, top: view.pieces[piece].top },
            ),
        ),
        ...Object.entries(centreCorners(geometry)).flatMap(([corner, point]) =>
            pointValues(`--geo-shown-centre-${corner}`, showPiecePoint(view, "core", point)),
        ),
        ...SEAT_POSITIONS.flatMap((seat) =>
            pointValues(
                `--geo-shown-callout-${seat}`,
                showPiecePoint(view, "core", calloutSpot(geometry, seat)),
            ),
        ),
        ...SEAT_POSITIONS.flatMap((seat) =>
            pointValues(
                `--geo-shown-plate-${seat}`,
                showPiecePoint(view, "core", plateAnchor(geometry, seat)),
            ),
        ),
    ];
}

export {
    TABLE_PIECES,
    projectPoint,
    shownPiece,
    showPiecePoint,
    tableView,
    tableViewValues,
    unprojectPoint,
};
export type { PiecePose, PlanePoint, TableCamera, TablePiece, TableView };
