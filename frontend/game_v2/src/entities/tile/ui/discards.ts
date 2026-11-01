import { html } from "lit-html";

import { RIVER_ROWS, RIVER_ROW_SIZE, type RiverOverflow } from "@/entities/tile/lib/river-shape";
import { type TileFace } from "@/entities/tile/lib/tile-utils";

import { Tile } from "./tile";

interface DiscardTile {
    face: TileFace;
    riichi?: boolean;
    /** The table's latest discard, still where it fell. */
    last?: boolean;
}

/** The row a discard lies in: six to a row, the last row taking every tile past the full ones. */
function rowOf(index: number, overflow: RiverOverflow): number {
    return Math.min(RIVER_ROWS[overflow] - 1, Math.floor(index / RIVER_ROW_SIZE));
}

/** Render a player's discard pile as rows of six, past three rows as `overflow` says. */
function Discards(tiles: readonly DiscardTile[], overflow: RiverOverflow = "run-on") {
    const rows: DiscardTile[][] = [];
    for (const [index, tile] of tiles.entries()) {
        const row = rowOf(index, overflow);
        rows[row] = [...(rows[row] ?? []), tile];
    }

    return html`<span class="discards"
        >${rows.map(
            (row) =>
                html`<span class="discard-row"
                    >${row.map((t) => {
                        const classes = ["discard-tile"];
                        if (t.riichi) {
                            classes.push("discard-tile-riichi");
                        }
                        if (t.last) {
                            classes.push("discard-tile--last");
                        }
                        return html`<span class="${classes.join(" ")}">${Tile(t.face, "face")}</span>`;
                    })}</span
                >`,
        )}</span
    >`;
}

export { Discards };
export type { DiscardTile };
