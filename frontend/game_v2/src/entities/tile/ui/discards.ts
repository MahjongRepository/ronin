import { html, nothing } from "lit-html";

import { RIVER_ROWS, RIVER_ROW_SIZE, type RiverOverflow } from "@/entities/tile/lib/river-shape";
import { type SeatTurn } from "@/entities/tile/lib/tile-body";
import { type TileFace } from "@/entities/tile/lib/tile-utils";

import { Tile, lyingSlotStyle } from "./tile";

interface DiscardTile {
    readonly tileId?: number;
    readonly tsumogiri?: boolean;
    face: TileFace;
    riichi?: boolean;
    /** The table's latest discard, still where it fell. */
    last?: boolean;
}

/** The row a discard lies in: six to a row, the last row taking every tile past the full ones. */
function rowOf(index: number, overflow: RiverOverflow): number {
    return Math.min(RIVER_ROWS[overflow] - 1, Math.floor(index / RIVER_ROW_SIZE));
}

interface RiverPlace {
    readonly rowsAfter: number;
    readonly tilesAfter: number;
}

function paintOrder(turn: SeatTurn, { rowsAfter, tilesAfter }: RiverPlace) {
    if (turn === 180) {
        return `z-index: ${rowsAfter + 1}`;
    }
    if (turn === 270) {
        return `z-index: ${tilesAfter + 1}`;
    }
    return nothing;
}

function riichiSlotStyle(turn: SeatTurn, paint: string | typeof nothing): string {
    const slot = lyingSlotStyle({ turn });
    return paint === nothing ? slot : `${paint}; ${slot}`;
}

/** Render a player's discard pile as rows of six, past three rows as `overflow` says. */
function Discards(
    tiles: readonly DiscardTile[],
    overflow: RiverOverflow = "run-on",
    turn: SeatTurn = 0,
) {
    const rows: DiscardTile[][] = [];
    for (const [index, tile] of tiles.entries()) {
        const row = rowOf(index, overflow);
        rows[row] = [...(rows[row] ?? []), tile];
    }

    return html`<span class="discards"
        >${rows.map(
            (row, rowIndex) =>
                html`<span class="discard-row"
                    >${row.map((t, index) => {
                        const classes = ["discard-tile"];
                        if (t.riichi) {
                            classes.push("discard-tile-riichi");
                        }
                        if (t.last) {
                            classes.push("discard-tile--last");
                        }
                        const order = paintOrder(turn, {
                            rowsAfter: rows.length - 1 - rowIndex,
                            tilesAfter: row.length - 1 - index,
                        });
                        const paint = t.riichi === true ? riichiSlotStyle(turn, order) : order;
                        return html`<span class="${classes.join(" ")}" style=${paint} data-tile-id=${t.tileId ?? ""} data-tsumogiri=${t.tsumogiri === true}>${Tile(t.face, "face", { sideways: t.riichi === true, turn })}</span>`;
                    })}</span
                >`,
        )}</span
    >`;
}

export { Discards };
export type { DiscardTile };
