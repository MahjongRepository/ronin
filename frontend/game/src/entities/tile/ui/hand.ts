import { html } from "lit-html";

import { type TileFace } from "@/entities/tile/lib/tile-utils";

import { Tile } from "./tile";

type HandTile = {
    face: TileFace;
    show: "face" | "back";
};

/** Render a horizontal row of mahjong tiles with an optional drawn tile separated by a gap. */
function Hand(tiles: HandTile[], drawnTile?: HandTile) {
    return html`<span class="hand"
        >${tiles.map((t) => html`<span class="hand-tile">${Tile(t.face, t.show)}</span>`)}${
            drawnTile
                ? html`<span class="hand-tile hand-drawn-gap">${Tile(drawnTile.face, drawnTile.show)}</span>`
                : ""
        }</span
    >`;
}

export { Hand };
export type { HandTile };
