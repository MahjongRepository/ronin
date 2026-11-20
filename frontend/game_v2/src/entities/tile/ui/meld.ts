import { type TemplateResult, html, nothing } from "lit-html";

import { type MeldTile } from "@/entities/tile/lib/meld-tiles";
import { type SeatTurn } from "@/entities/tile/lib/tile-body";

import { Tile, type TileLayout, lyingSlotStyle } from "./tile";

interface MeldLayout {
    readonly turn?: SeatTurn;
}

function tileLayout({ turn }: MeldLayout, sideways: boolean, joined = false): TileLayout {
    return { joined, lay: "lying", sideways, turn };
}

function slotWrapperStyle(layout: MeldLayout, paint: string | typeof nothing): string {
    const slot = lyingSlotStyle(tileLayout(layout, true));
    return paint === nothing ? slot : `${paint}; ${slot}`;
}

/**
 * An added kan's pair: on the bottom and top strips one tile lies on screen below the other, laid against its edge
 * and painted over it; on a side strip they lie side by side, joined only as the whole slot is.
 */
interface MeldSlot {
    readonly joined: boolean;
    readonly paint: string | typeof nothing;
}

function StackedTile(
    tile: Extract<MeldTile, { kind: "stacked" }>,
    layout: MeldLayout,
    { joined, paint }: MeldSlot,
): TemplateResult {
    const across = layout.turn === 90 || layout.turn === 270;
    const lower = layout.turn === 180 ? "top" : "bottom";
    function joinedPart(part: "bottom" | "top"): boolean {
        return joined || (!across && part === lower);
    }
    const bottom = html`<span class="meld-tile-stacked-bottom meld-tile-sideways" data-tile-id=${tile.bottomId ?? ""}>${Tile(tile.bottom, "face", tileLayout(layout, true, joinedPart("bottom")))}</span>`;
    const top = html`<span class="meld-tile-stacked-top meld-tile-sideways" data-tile-id=${tile.topId ?? ""}>${Tile(tile.top, "face", tileLayout(layout, true, joinedPart("top")))}</span>`;
    const parts = layout.turn === 180 ? [bottom, top] : [top, bottom];
    return html`<span class="meld-tile meld-tile-stacked" style=${slotWrapperStyle(layout, paint)}>${parts}</span>`;
}

function MeldTileView(tile: MeldTile, layout: MeldLayout, slot: MeldSlot): TemplateResult {
    const { joined, paint } = slot;
    switch (tile.kind) {
        case "upright": {
            return html`<span class="meld-tile" style=${paint} data-tile-id=${tile.tileId ?? ""}>${Tile(tile.face, "face", tileLayout(layout, false, joined))}</span>`;
        }
        case "sideways": {
            return html`<span class="meld-tile meld-tile-sideways" style=${slotWrapperStyle(layout, paint)} data-tile-id=${tile.tileId ?? ""}>${Tile(tile.face, "face", tileLayout(layout, true, joined))}</span>`;
        }
        case "facedown": {
            return html`<span class="meld-tile" style=${paint} data-tile-id=${tile.tileId ?? ""}>${Tile(tile.face, "back", tileLayout(layout, false, joined))}</span>`;
        }
        case "stacked": {
            return StackedTile(tile, layout, slot);
        }
    }
}

function paintOrder({ turn }: MeldLayout, index: number, count: number) {
    return turn === 270 ? `z-index: ${count - index}` : nothing;
}

/** Whether a side strip's meld tile lies against the edge of the tile above it on screen, painted over it. */
function joinedInMeld({ turn }: MeldLayout, index: number, count: number): boolean {
    if (turn === 90) {
        return index > 0;
    }
    return turn === 270 && index < count - 1;
}

/** Render a meld from its laid tiles (`meldTiles` lays a recorded meld out), faces like a hand's and a river's. */
function Meld(tiles: readonly MeldTile[], layout: MeldLayout = {}): TemplateResult {
    return html`<span class="meld"
        >${tiles.map((tile, index) =>
            MeldTileView(tile, layout, {
                joined: joinedInMeld(layout, index, tiles.length),
                paint: paintOrder(layout, index, tiles.length),
            }),
        )}</span
    >`;
}

export { Meld };
export type { MeldLayout };
