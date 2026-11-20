import { type TemplateResult, html, nothing } from "lit-html";

import { type MeldTile } from "@/entities/tile/lib/meld-tiles";
import { type SeatTurn } from "@/entities/tile/lib/tile-body";

import { Tile, type TileLayout, lyingSlotStyle } from "./tile";

interface MeldLayout {
    readonly turn?: SeatTurn;
}

function tileLayout({ turn }: MeldLayout, sideways: boolean): TileLayout {
    return { lay: "lying", sideways, turn };
}

function slotWrapperStyle(layout: MeldLayout, paint: string | typeof nothing): string {
    const slot = lyingSlotStyle(tileLayout(layout, true));
    return paint === nothing ? slot : `${paint}; ${slot}`;
}

function StackedTile(
    tile: Extract<MeldTile, { kind: "stacked" }>,
    layout: MeldLayout,
    paint: string | typeof nothing,
): TemplateResult {
    const bottom = html`<span class="meld-tile-stacked-bottom meld-tile-sideways" data-tile-id=${tile.bottomId ?? ""}>${Tile(tile.bottom, "face", tileLayout(layout, true))}</span>`;
    const top = html`<span class="meld-tile-stacked-top meld-tile-sideways" data-tile-id=${tile.topId ?? ""}>${Tile(tile.top, "face", tileLayout(layout, true))}</span>`;
    const parts = layout.turn === 180 ? [bottom, top] : [top, bottom];
    return html`<span class="meld-tile meld-tile-stacked" style=${slotWrapperStyle(layout, paint)}>${parts}</span>`;
}

function MeldTileView(
    tile: MeldTile,
    layout: MeldLayout,
    paint: string | typeof nothing,
): TemplateResult {
    switch (tile.kind) {
        case "upright": {
            return html`<span class="meld-tile" style=${paint} data-tile-id=${tile.tileId ?? ""}>${Tile(tile.face, "face", tileLayout(layout, false))}</span>`;
        }
        case "sideways": {
            return html`<span class="meld-tile meld-tile-sideways" style=${slotWrapperStyle(layout, paint)} data-tile-id=${tile.tileId ?? ""}>${Tile(tile.face, "face", tileLayout(layout, true))}</span>`;
        }
        case "facedown": {
            return html`<span class="meld-tile" style=${paint} data-tile-id=${tile.tileId ?? ""}>${Tile(tile.face, "back", tileLayout(layout, false))}</span>`;
        }
        case "stacked": {
            return StackedTile(tile, layout, paint);
        }
    }
}

function paintOrder({ turn }: MeldLayout, index: number, count: number) {
    return turn === 270 ? `z-index: ${count - index}` : nothing;
}

/** Render a meld from its laid tiles (`meldTiles` lays a recorded meld out), faces like a hand's and a river's. */
function Meld(tiles: readonly MeldTile[], layout: MeldLayout = {}): TemplateResult {
    return html`<span class="meld"
        >${tiles.map((tile, index) => MeldTileView(tile, layout, paintOrder(layout, index, tiles.length)))}</span
    >`;
}

export { Meld };
export type { MeldLayout };
