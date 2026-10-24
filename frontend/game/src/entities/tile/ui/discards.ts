import { html } from "lit-html";

import { type TileFace } from "@/entities/tile/lib/tile-utils";

import { Tile } from "./tile";

type DiscardTile = {
    face: TileFace;
    grayed?: boolean;
    riichi?: boolean;
};

const ROW_SIZE = 6;
const MAX_FULL_ROWS = 2;

/** Render a player's discard pile as rows of tiles (6 per row, 3 rows max, row 3 overflows). */
function Discards(tiles: DiscardTile[]) {
    const rows: DiscardTile[][] = [];

    for (let i = 0; i < tiles.length; i++) {
        const rowIndex = i < ROW_SIZE * MAX_FULL_ROWS ? (i / ROW_SIZE) | 0 : MAX_FULL_ROWS;
        if (!rows[rowIndex]) {
            rows[rowIndex] = [];
        }
        rows[rowIndex].push(tiles[i]);
    }

    return html`<span class="discards"
        >${rows.map(
            (row) =>
                html`<span class="discard-row"
                    >${row.map((t) => {
                        const classes = ["discard-tile"];
                        if (t.grayed) {
                            classes.push("discard-tile-grayed");
                        }
                        if (t.riichi) {
                            classes.push("discard-tile-riichi");
                        }
                        return html`<span class="${classes.join(" ")}">${Tile(t.face, "face")}</span>`;
                    })}</span
                >`,
        )}</span
    >`;
}

export { Discards };
export type { DiscardTile };
