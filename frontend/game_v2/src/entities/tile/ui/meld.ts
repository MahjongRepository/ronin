import { type TemplateResult, html } from "lit-html";

import { type MeldTile } from "@/entities/tile/lib/meld-tiles";

import { Tile } from "./tile";

function MeldTileView(tile: MeldTile): TemplateResult {
    switch (tile.kind) {
        case "upright": {
            return html`<span class="meld-tile">${Tile(tile.face, "face")}</span>`;
        }
        case "sideways": {
            return html`<span class="meld-tile meld-tile-sideways">${Tile(tile.face, "face")}</span>`;
        }
        case "facedown": {
            return html`<span class="meld-tile">${Tile(tile.face, "back")}</span>`;
        }
        case "stacked": {
            return html`<span class="meld-tile meld-tile-stacked">
                <span class="meld-tile-stacked-bottom meld-tile-sideways">${Tile(tile.bottom, "face")}</span>
                <span class="meld-tile-stacked-top meld-tile-sideways">${Tile(tile.top, "face")}</span>
            </span>`;
        }
    }
}

/**
 * Render a meld from its laid tiles (`meldTiles` lays a recorded meld out), faces like a hand's and a river's; a meld an
 * offer refers to (a kan a chankan may rob) is marked as the offer's source.
 */
function Meld(tiles: readonly MeldTile[], source = false): TemplateResult {
    return html`<span class="meld ${source ? "meld--source" : ""}">${tiles.map(MeldTileView)}</span>`;
}

export { Meld };
