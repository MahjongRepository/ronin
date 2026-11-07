import { type MotionRect, type MotionTile } from "@/entities/table/lib/board-motion";
import { SEAT_POSITIONS, type SeatPosition } from "@/entities/table/model/board-types";

export interface TilePose {
    readonly width: number;
    readonly height: number;
    readonly angle: number;
    readonly standing: number;
}

export interface TileSnapshot extends MotionTile {
    readonly pose: TilePose;
    readonly scale: number;
    readonly element: HTMLElement;
    readonly image: HTMLElement;
}

export const SEAT_TURNS: Readonly<Record<SeatPosition, number>> = {
    bottom: 0,
    left: 90,
    right: 270,
    top: 180,
};
const TILE_FEEDBACK_STYLE = ["filter", "outline", "outline-offset"];
const TILE_STYLE = [
    ...TILE_FEEDBACK_STYLE,
    "background",
    "border-radius",
    "color",
    "font-size",
    "box-sizing",
];

export function refreshTileFeedback(source: HTMLElement, image: HTMLElement): void {
    const face = image.querySelector<HTMLElement>(":scope > .tile");
    if (face === null) {
        return;
    }
    const style = getComputedStyle(source);
    for (const name of TILE_FEEDBACK_STYLE) {
        face.style.setProperty(name, style.getPropertyValue(name));
    }
}

function isSideways(tile: HTMLElement): boolean {
    return tile.parentElement?.matches(".meld-tile-sideways, .discard-tile-riichi") === true;
}

function capturePose(tile: HTMLElement, rect: MotionRect, seat: SeatPosition): TilePose {
    const angle = SEAT_TURNS[seat] + (isSideways(tile) ? 90 : 0);
    return {
        angle,
        height: angle % 180 === 0 ? rect.height : rect.width,
        standing:
            tile.closest(".board-local .hand") !== null && !tile.classList.contains("tile-back")
                ? 1
                : 0,
        width: angle % 180 === 0 ? rect.width : rect.height,
    };
}

function copiedTileStyle(tile: HTMLElement): readonly string[] {
    return isSideways(tile) ? TILE_STYLE.filter((name) => name !== "border-radius") : TILE_STYLE;
}

function copyTile(tile: HTMLElement, pose: TilePose): HTMLElement {
    const face = tile.cloneNode(true);
    if (!(face instanceof HTMLElement)) {
        throw new Error("A board tile must be an HTML element");
    }
    const style = getComputedStyle(tile);
    for (const name of copiedTileStyle(tile)) {
        face.style.setProperty(name, style.getPropertyValue(name));
    }
    face.style.visibility = "visible";
    const image = createImage(tile, pose);
    image.append(face);
    return image;
}

function createImage(tile: HTMLElement, pose: TilePose): HTMLElement {
    const image = document.createElement("span");
    image.className = "board-motion__tile";
    image.classList.toggle(
        "board-motion__tile--individual",
        tile.parentElement instanceof HTMLButtonElement,
    );
    image.style.setProperty("--motion-width", `${pose.width}px`);
    image.style.setProperty("--motion-height", `${pose.height}px`);
    image.style.setProperty("--motion-angle", `${pose.angle}deg`);
    image.style.setProperty("--motion-standing", String(pose.standing));
    return image;
}

function measureScale(tile: HTMLElement, rect: MotionRect, seat: SeatPosition): number {
    const width = Number.parseFloat(getComputedStyle(tile).width);
    const drawnWidth = SEAT_TURNS[seat] % 180 === 0 ? rect.width : rect.height;
    return width > 0 && drawnWidth > 0 ? drawnWidth / width : 1;
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
    const rect = tile.getBoundingClientRect();
    const pose = capturePose(tile, rect, location.seat);
    return [
        {
            ...location,
            concealed: tile.classList.contains("tile-back"),
            drawn,
            element: tile,
            id,
            image: copyTile(tile, pose),
            key: `${location.seat}-${location.region}-${id === "" ? slot : id}`,
            pose,
            rect,
            scale: measureScale(tile, rect, location.seat),
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

export function centerOrigin(board: HTMLElement, target: TileSnapshot): MotionRect {
    const center =
        board.querySelector("[data-area='center']")?.getBoundingClientRect() ??
        board.getBoundingClientRect();
    return {
        height: target.rect.height,
        left: center.left + (center.width - target.rect.width) / 2,
        top: center.top + (center.height - target.rect.height) / 2,
        width: target.rect.width,
    };
}
