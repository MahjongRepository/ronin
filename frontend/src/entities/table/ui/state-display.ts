import { type TemplateResult, html, nothing } from "lit-html";

import { type TableState } from "@/entities/table/model/types";

import { GameEndDisplay } from "./game-end-display";
import { PlayerPanel } from "./player-panel";
import { RoundEndDisplay } from "./round-end-display";
import { TableInfo } from "./table-info";

/**
 * Render the full game state display: table info bar, optional result panel,
 * and 4 player panels stacked vertically with dealer and current-turn indicators.
 */
function StateDisplay(state: TableState): TemplateResult {
    let resultPanel: TemplateResult | typeof nothing = nothing;

    if (state.phase === "round_ended" && state.roundEndResult) {
        resultPanel = RoundEndDisplay(state.roundEndResult, state.players, state.dealerSeat);
    } else if (state.phase === "game_ended" && state.gameEndResult) {
        resultPanel = GameEndDisplay(state.gameEndResult, state.players);
    }

    return html`<div class="state-display">
        ${TableInfo(state)}
        ${resultPanel}
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
