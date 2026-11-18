import { type MotionRect, type MotionTile } from "@/entities/table/lib/board-motion";
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
    readonly scales: TileScales;
    readonly element: HTMLElement;
    readonly image: HTMLElement;
}

const TILE_STYLE = ["filter", "outline", "outline-offset", "color", "font-size", "box-sizing"];

function isSideways(tile: HTMLElement): boolean {
    return tile.parentElement?.matches(".meld-tile-sideways, .discard-tile-riichi") === true;
}

function standingOf(tile: Element): number {
    return tile.classList.contains("tile--standing") ? 1 : 0;
}

function screenDownShare(tile: HTMLElement, seat: SeatPosition): number {
    const name = SEAT_TURNS[seat] % 180 === 0 ? "--slot-down-share" : "--slot-across-share";
    const share = Number.parseFloat(tile.style.getPropertyValue(name));
    return Number.isFinite(share) ? share : 1;
}

function capturePose(tile: HTMLElement, rect: MotionRect, seat: SeatPosition): TilePose {
    const angle = SEAT_TURNS[seat] + (isSideways(tile) ? 90 : 0);
    const lying = tile.closest(".board-local .meld") !== null;
    const unsquashedHeight = rect.height / screenDownShare(tile, seat);
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

function measureOnGrid(slot: HTMLElement, tile: HTMLElement): MotionRect {
    slot.style.setProperty("translate", "none", "important");
    const rect = tile.getBoundingClientRect();
    slot.style.removeProperty("translate");
    return rect;
}

type TilePlace = Pick<TileSnapshot, "latest" | "painted" | "rect">;

function measurePlace(slot: HTMLElement, tile: HTMLElement): TilePlace {
    const latest = slot.classList.contains("discard-tile--last");
    const rect = latest ? measureOnGrid(slot, tile) : tile.getBoundingClientRect();
    const painted = latest ? tile.getBoundingClientRect() : rect;
    return { latest, painted, rect };
}

function captureTile(
    element: HTMLElement,
    location: Pick<MotionTile, "seat" | "region" | "index">,
): TileSnapshot[] {
    const tile = element.querySelector<HTMLElement>(":scope > .tile");
    if (tile === null) {
        return [];
    }
    const id = element.dataset.tileId ?? "";
    const drawn = element.classList.contains("hand-drawn-gap");
    const slot = drawn ? "drawn" : `slot-${location.index}`;
    const place = measurePlace(element, tile);
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

function captureSeat(board: HTMLElement, seat: SeatPosition): TileSnapshot[] {
    return (["hand", "discards", "melds"] as const).flatMap((region) => {
        const area = board.querySelector(`[data-area="${seat}-${region}"]`);
        if (area === null) {
            return [];
        }
        return [...area.querySelectorAll<HTMLElement>("[data-tile-id]")].flatMap((element, index) =>
            captureTile(element, { index, region, seat }),
        );
    });
}

export function snapshotTiles(board: HTMLElement): readonly TileSnapshot[] {
    const tiles = SEAT_POSITIONS.flatMap((seat) => captureSeat(board, seat));
    const dora = [...board.querySelectorAll<HTMLElement>(".board-dora__tile")].flatMap(
        (element, index) => captureTile(element, { index, region: "dora", seat: "bottom" }),
    );
    return [...tiles, ...dora];
}
