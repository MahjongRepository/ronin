import { OWN_LYING_HEIGHT_SHARE } from "@/entities/table/lib/board-constants";
import { type MotionRect, type MotionTile } from "@/entities/table/lib/board-motion";
import {
    type PieceFrame,
    type TileQuad,
    pieceOrigin,
    rectQuad,
    tiltedQuad,
} from "@/entities/table/lib/tile-quad";
import { SEAT_POSITIONS, SEAT_TURNS, type SeatPosition } from "@/entities/table/model/board-types";

export interface TilePose {
    readonly width: number;
    readonly height: number;
    readonly angle: number;
    readonly standing: number;
    readonly lying: number;
}

/** How much larger the screen shows a tile than it is laid, across and down the screen. */
export interface TileScales {
    readonly across: number;
    readonly down: number;
}

export interface TileSnapshot extends MotionTile {
    readonly pose: TilePose;
    /** The tile's corners as the camera shows them: its bounding box's, off the tilted table. */
    readonly quad: TileQuad;
    readonly paintedQuad: TileQuad;
    readonly scales: TileScales;
    readonly element: HTMLElement;
    readonly image: HTMLElement;
}

/**
 * What one snapshot has read of each tile's ancestors: a tilted piece's camera on the screen (its `matrix3d` and its
 * box's top left corner), else null; each element read once.
 */
type PieceFrames = Map<Element, PieceFrame | null>;

const TILE_STYLE = ["filter", "outline", "outline-offset", "color", "font-size", "box-sizing"];

function isSideways(tile: HTMLElement): boolean {
    return tile.parentElement?.matches(".meld-tile-sideways, .discard-tile-riichi") === true;
}

export function standingOf(tile: Element): number {
    return tile.classList.contains("tile--standing") ? 1 : 0;
}

function capturePose(tile: HTMLElement, rect: MotionRect, seat: SeatPosition): TilePose {
    const angle = SEAT_TURNS[seat] + (isSideways(tile) ? 90 : 0);
    const lying = tile.closest(".board-local .meld") !== null;
    const unsquashedHeight = lying ? rect.height / OWN_LYING_HEIGHT_SHARE : rect.height;
    return {
        angle,
        height: angle % 180 === 0 ? unsquashedHeight : rect.width,
        lying: lying ? 1 : 0,
        standing: standingOf(tile),
        width: angle % 180 === 0 ? rect.width : unsquashedHeight,
    };
}

function copyTile(tile: HTMLElement, pose: TilePose): HTMLElement {
    const face = tile.cloneNode(true);
    if (!(face instanceof HTMLElement)) {
        throw new Error("A board tile must be an HTML element");
    }
    const style = getComputedStyle(tile);
    for (const name of TILE_STYLE) {
        face.style.setProperty(name, style.getPropertyValue(name));
    }
    face.style.visibility = "visible";
    const image = createImage(tile, pose);
    image.append(face);
    return image;
}

function imageClasses(tile: HTMLElement): readonly string[] {
    const tsumogiri = tile.parentElement?.dataset.tsumogiri === "true";
    return ["board-motion__tile", ...(tsumogiri ? ["board-motion__tile--tsumogiri"] : [])];
}

function createImage(tile: HTMLElement, pose: TilePose): HTMLElement {
    const image = document.createElement("span");
    image.classList.add(...imageClasses(tile));
    image.style.setProperty("--motion-width", `${pose.width}px`);
    image.style.setProperty("--motion-height", `${pose.height}px`);
    image.style.setProperty("--motion-angle", `${pose.angle}deg`);
    return image;
}

function measureScales(tile: HTMLElement, rect: MotionRect, seat: SeatPosition): TileScales {
    const style = getComputedStyle(tile);
    const [width, height] = [style.width, style.height].map((length) => Number.parseFloat(length));
    const upright = SEAT_TURNS[seat] % 180 === 0;
    const [drawnWidth, drawnHeight] = upright
        ? [rect.width, rect.height]
        : [rect.height, rect.width];
    const across = width !== undefined && width > 0 && drawnWidth > 0 ? drawnWidth / width : 1;
    const down =
        height !== undefined && height > 0 && drawnHeight > 0 ? drawnHeight / height : across;
    return upright ? { across, down } : { across: down, down: across };
}

function readPieceFrame(piece: HTMLElement): PieceFrame | null {
    const { transform } = getComputedStyle(piece);
    if (!transform.startsWith("matrix3d")) {
        return null;
    }
    const value = new DOMMatrixReadOnly(transform);
    const matrix = [
        value.m11,
        value.m12,
        value.m13,
        value.m14,
        value.m21,
        value.m22,
        value.m23,
        value.m24,
        value.m31,
        value.m32,
        value.m33,
        value.m34,
        value.m41,
        value.m42,
        value.m43,
        value.m44,
    ];
    const box = {
        height: piece.offsetHeight,
        left: -piece.clientLeft,
        top: -piece.clientTop,
        width: piece.offsetWidth,
    };
    return { matrix, origin: pieceOrigin(matrix, box, piece.getBoundingClientRect()) };
}

function cachedFrame(element: HTMLElement, frames: PieceFrames): PieceFrame | null {
    if (!frames.has(element)) {
        frames.set(element, readPieceFrame(element));
    }
    return frames.get(element) ?? null;
}

/** The camera of the tilted piece a tile lies on: its nearest ancestor drawn through a `matrix3d`, if any. */
function tiltedFrame(tile: HTMLElement, frames: PieceFrames): PieceFrame | null {
    for (let element = tile.parentElement; element !== null; element = element.parentElement) {
        const frame = cachedFrame(element, frames);
        if (frame !== null) {
            return frame;
        }
    }
    return null;
}

/**
 * A tile's corners on the screen: on a tilted piece as its camera shows them, else its bounding box's. A camera that
 * rolls the piece's rows cannot be read back from a bounding box, and fails loudly rather than flying the tile flat.
 */
function captureQuad(tile: HTMLElement, rect: MotionRect, frames: PieceFrames): TileQuad {
    const frame = tiltedFrame(tile, frames);
    if (frame === null) {
        return rectQuad(rect);
    }
    const quad = tiltedQuad(frame, rect);
    if (quad === null) {
        throw new Error("A tilted piece's camera must keep its rows level");
    }
    return quad;
}

function measureOnGrid(slot: HTMLElement, tile: HTMLElement): MotionRect {
    slot.style.setProperty("translate", "none", "important");
    const rect = tile.getBoundingClientRect();
    slot.style.removeProperty("translate");
    return rect;
}

type TilePlace = Pick<TileSnapshot, "latest" | "painted" | "paintedQuad" | "quad" | "rect">;

function measurePlace(slot: HTMLElement, tile: HTMLElement, frames: PieceFrames): TilePlace {
    const latest = slot.classList.contains("discard-tile--last");
    const rect = latest ? measureOnGrid(slot, tile) : tile.getBoundingClientRect();
    const painted =
        latest && !slot.hasAttribute("data-landing") ? tile.getBoundingClientRect() : rect;
    const quad = captureQuad(tile, rect, frames);
    return {
        latest,
        painted,
        paintedQuad: painted === rect ? quad : captureQuad(tile, painted, frames),
        quad,
        rect,
    };
}

function captureTile(
    element: HTMLElement,
    location: Pick<MotionTile, "seat" | "region" | "index">,
    frames: PieceFrames,
): TileSnapshot[] {
    const tile = element.querySelector<HTMLElement>(":scope > .tile");
    if (tile === null) {
        return [];
    }
    const id = element.dataset.tileId ?? "";
    const drawn = element.classList.contains("hand-drawn-gap");
    const slot = drawn ? "drawn" : `slot-${location.index}`;
    const place = measurePlace(element, tile, frames);
    const pose = capturePose(tile, place.rect, location.seat);
    return [
        {
            ...location,
            concealed: tile.classList.contains("tile-back"),
            drawn,
            element: tile,
            id,
            image: copyTile(tile, pose),
            key: `${location.seat}-${location.region}-${id === "" ? slot : id}`,
            ...place,
            pose,
            scales: measureScales(tile, place.rect, location.seat),
            tsumogiri: element.dataset.tsumogiri === "true",
        },
    ];
}

function captureSeat(board: HTMLElement, seat: SeatPosition, frames: PieceFrames): TileSnapshot[] {
    return (["hand", "discards", "melds"] as const).flatMap((region) => {
        const area = board.querySelector(`[data-area="${seat}-${region}"]`);
        if (area === null) {
            return [];
        }
        return [...area.querySelectorAll<HTMLElement>("[data-tile-id]")].flatMap((element, index) =>
            captureTile(element, { index, region, seat }, frames),
        );
    });
}

export function snapshotTiles(board: HTMLElement): readonly TileSnapshot[] {
    const frames: PieceFrames = new Map();
    const tiles = SEAT_POSITIONS.flatMap((seat) => captureSeat(board, seat, frames));
    const dora = [...board.querySelectorAll<HTMLElement>(".board-dora__tile")].flatMap(
        (element, index) => captureTile(element, { index, region: "dora", seat: "bottom" }, frames),
    );
    return [...tiles, ...dora];
}
