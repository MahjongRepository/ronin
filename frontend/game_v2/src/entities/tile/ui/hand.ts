import { html } from "lit-html";

import { type TileFace } from "@/entities/tile/lib/tile-utils";

import { Tile, TileBack } from "./tile";

/**
 * A tile in a hand: one the view knows, with its tile id when it came from a table, shown face up or as a back by
 * the display's choice; or a concealed one, known only by its hand's count, which is always a back.
 */
type HandTile =
    | { readonly face: TileFace; readonly show: "face" | "back"; readonly tileId?: number }
    | { readonly face?: undefined; readonly show: "concealed"; readonly tileId?: undefined };

function HandTileView(tile: HandTile) {
    return tile.show === "concealed" ? TileBack() : Tile(tile.face, tile.show);
}

/** Render a horizontal row of mahjong tiles with an optional drawn tile separated by a gap. */
function Hand(tiles: readonly HandTile[], drawnTile?: HandTile) {
    return html`<span class="hand"
        >${tiles.map((t) => html`<span class="hand-tile">${HandTileView(t)}</span>`)}${
            drawnTile
                ? html`<span class="hand-tile hand-drawn-gap">${HandTileView(drawnTile)}</span>`
                : ""
        }</span
    >`;
}

export { Hand };
export type { HandTile };
