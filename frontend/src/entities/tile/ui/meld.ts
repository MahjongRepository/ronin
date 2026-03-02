import { html } from "lit-html";

import { type TileFace } from "@/entities/tile/lib/tile-utils";

import { Tile } from "./tile";

type MeldTileDisplay =
    | { kind: "upright"; face: TileFace }
    | { kind: "sideways"; face: TileFace }
    | { kind: "facedown"; face: TileFace }
    | { kind: "stacked"; bottom: TileFace; top: TileFace };

function MeldTile(tile: MeldTileDisplay) {
    switch (tile.kind) {
        case "upright":
            return html`<span class="meld-tile">${Tile(tile.face, "face")}</span>`;
        case "sideways":
            return html`<span class="meld-tile meld-tile-sideways">${Tile(tile.face, "face")}</span>`;
        case "facedown":
            return html`<span class="meld-tile">${Tile(tile.face, "back")}</span>`;
        case "stacked":
            return html`<span class="meld-tile meld-tile-stacked">
                <span class="meld-tile-stacked-bottom meld-tile-sideways">${Tile(tile.bottom, "face")}</span>
                <span class="meld-tile-stacked-top meld-tile-sideways">${Tile(tile.top, "face")}</span>
            </span>`;
    }
}

function Meld(tiles: MeldTileDisplay[]) {
    return html`<span class="meld">${tiles.map(MeldTile)}</span>`;
}

export { Meld };
export type { MeldTileDisplay };
