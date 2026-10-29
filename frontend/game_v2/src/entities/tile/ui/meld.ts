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

/** Render a meld from its laid tiles (`meldTiles` lays a recorded meld out), faces like a hand's and a river's. */
function Meld(tiles: readonly MeldTile[]): TemplateResult {
    return html`<span class="meld">${tiles.map(MeldTileView)}</span>`;
}

export { Meld };
