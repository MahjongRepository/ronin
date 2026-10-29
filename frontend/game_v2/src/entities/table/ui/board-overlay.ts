import { type TemplateResult } from "lit-html";

import { roundEndDisplay } from "@/entities/table/lib/round-end-display";
import { type TableState } from "@/entities/table/model/types";

import { GameEndDisplay } from "./game-end-display";
import { GameStartDisplay } from "./game-start-display";
import { RoundEndDisplay } from "./round-end-display";

/**
 * The page of a round's result the view shows, and its way to change it; without it the first page shows. A page out
 * of range shows the nearest.
 */
export interface ResultPaging {
    readonly page: number;
    readonly onPage?: (page: number) => void;
}

/**
 * The panel a table shows over its board: the seating once the game starts, until its first deal; the round's
 * result once it ends, at the page the view picked; the standings once the game does.
 */
export function boardOverlay(
    table: TableState,
    paging: ResultPaging = { page: 0 },
): TemplateResult | undefined {
    if (table.phase === "pre_game" && table.players.length > 0) {
        return GameStartDisplay(table.players, table.firstDealerSeat);
    }
    if (table.phase === "round_ended" && table.roundEndResult) {
        return RoundEndDisplay({
            display: roundEndDisplay(
                {
                    dealerSeat: table.dealerSeat,
                    players: table.players,
                    result: table.roundEndResult,
                },
                paging.page,
            ),
            onPage: paging.onPage,
        });
    }
    if (table.phase === "game_ended" && table.gameEndResult) {
        return GameEndDisplay(table.gameEndResult, table.players);
    }
    return undefined;
}
