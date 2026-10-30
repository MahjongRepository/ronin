import { html } from "lit-html";

import { type TileFace } from "@/entities/tile/lib/tile-utils";

import { Tile } from "./tile";

interface DiscardTile {
    face: TileFace;
    riichi?: boolean;
    /** The table's latest discard, still where it fell. */
    last?: boolean;
}

/**
 * How a river past its normal three rows lies: a top or bottom river's third row runs on along its line (`run-on`), a
 * side river wraps its overflow into a fourth row of six toward its seat (`wrap`).
 */
type RiverOverflow = "run-on" | "wrap";

const ROW_SIZE = 6;

/** The row a discard lies in: six to a row, the last row taking every tile past the full ones. */
function rowOf(index: number, overflow: RiverOverflow): number {
    const lastRow = overflow === "wrap" ? 3 : 2;
    return Math.min(lastRow, Math.floor(index / ROW_SIZE));
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
export type { DiscardTile, RiverOverflow };
