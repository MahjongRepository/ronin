import { type TemplateResult } from "lit-html";

import { type TableState } from "@/entities/table/model/types";

import { GameEndDisplay } from "./game-end-display";
import { GameStartDisplay } from "./game-start-display";
import { RoundEndDisplay } from "./round-end-display";

/**
 * The panel a table shows over its board: the seating once the game starts, until its first deal; the round's
 * result once it ends; the standings once the game does.
 */
export function boardOverlay(table: TableState): TemplateResult | undefined {
    if (table.phase === "pre_game" && table.players.length > 0) {
        return GameStartDisplay(table.players, table.firstDealerSeat);
    }
    if (table.phase === "round_ended" && table.roundEndResult) {
        return RoundEndDisplay(table.roundEndResult, table.players, table.dealerSeat);
    }
    if (table.phase === "game_ended" && table.gameEndResult) {
        return GameEndDisplay(table.gameEndResult, table.players);
    }
    return undefined;
}
