import { type TemplateResult, html } from "lit-html";

import { windName } from "@/entities/table/lib/wind-name";
import { type TableState } from "@/entities/table/model/types";
import { Tile, tile136toString } from "@/entities/tile";

/**
 * Render a horizontal info bar showing round wind, dealer, dora indicators,
 * and stick counts.
 */
function TableInfo(state: TableState): TemplateResult {
    const roundDisplay = `${windName(state.roundWind)} ${state.roundNumber}`;
    const dealerName =
        state.players.find((p) => p.seat === state.dealerSeat)?.name ?? `Seat ${state.dealerSeat}`;

    return html`<div class="table-info">
        <span class="table-info__round">${roundDisplay}</span>
        <span class="table-info__dealer">Dealer: ${dealerName}</span>
        <span class="table-info__dora"
            >Dora:
            ${state.doraIndicators.map(
                (id) =>
                    html`<span class="table-info__dora-tile">${Tile(tile136toString(id), "face")}</span>`,
            )}</span
        >
        <span class="table-info__sticks"
            >Honba: ${state.honbaSticks} &middot; Riichi: ${state.riichiSticks}</span
        >
    </div>`;
}

export { TableInfo };
