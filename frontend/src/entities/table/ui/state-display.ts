import { type TemplateResult, html } from "lit-html";

import { type TableState } from "@/entities/table/model/types";

import { PlayerPanel } from "./player-panel";
import { TableInfo } from "./table-info";

/**
 * Render the full game state display: table info bar + 4 player panels
 * stacked vertically with dealer and current-turn indicators.
 */
function StateDisplay(state: TableState): TemplateResult {
    return html`<div class="state-display">
        ${TableInfo(state)}
        <div class="state-display__players">
            ${state.players.map((player) =>
                PlayerPanel(
                    player,
                    player.seat === state.dealerSeat,
                    player.seat === state.currentPlayerSeat,
                ),
            )}
        </div>
    </div>`;
}

export { StateDisplay };
