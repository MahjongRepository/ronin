import { type TemplateResult } from "lit-html";

import { gameEndDisplay } from "@/entities/table/lib/game-end-display";
import { type GameStartView, gameStartDisplay } from "@/entities/table/lib/game-start-display";
import { roundEndDisplay } from "@/entities/table/lib/round-end-display";
import { type TableState } from "@/entities/table/model/types";

import { GameEndDisplay } from "./game-end-display";
import { GameStartDisplay } from "./game-start-display";
import { type PanelAction } from "./panel-actions";
import { RoundEndDisplay } from "./round-end-display";

/**
 * The page of a round's result the view shows, and its way to change it; without it the first page shows. A page out
 * of range shows the nearest. The live game adds its controls to the result's head (its confirm), and shows the
 * game's last result over the game's end until the player dismisses it.
 */
export interface ResultPaging {
    readonly page: number;
    readonly onPage?: (page: number) => void;
    readonly controls?: TemplateResult;
    readonly overGameEnd?: boolean;
}

/** How the view shows the game's end: the seat it is read from (the live player's, none in a replay), its ways on. */
export interface GameEndView {
    readonly viewerSeat: number | null;
    readonly actions: readonly PanelAction[];
}

const NO_END_VIEW: GameEndView = { actions: [], viewerSeat: null };
const NO_START_VIEW: GameStartView = { secondsLeft: null, viewerSeat: null };
const FIRST_PAGE: ResultPaging = { page: 0 };

/** How the view shows each panel: the seating's, a result's page, the game end's; each left out shows its default. */
export interface OverlayView {
    readonly start?: GameStartView;
    readonly paging?: ResultPaging;
    readonly end?: GameEndView;
}

/**
 * Whether the panel a table shows over its board is its round's result: once the round ends, and once the game does
 * while the view still shows the last round's result over the game's end.
 */
export function showsRoundResult(table: TableState, overGameEnd = false): boolean {
    const shown = table.phase === "round_ended" || (table.phase === "game_ended" && overGameEnd);
    return shown && table.roundEndResult !== null;
}

/**
 * The panel a table shows over its board: the seating once the game starts, until its first deal, from the view's
 * seat with the start pause it counts down; the round's result once it ends, at the page the view picked; the
 * game's end once the game does, unless the view still shows the last round's result over it.
 */
export function boardOverlay(
    table: TableState,
    { end = NO_END_VIEW, paging = FIRST_PAGE, start = NO_START_VIEW }: OverlayView = {},
): TemplateResult | undefined {
    if (table.phase === "pre_game" && table.players.length > 0) {
        return GameStartDisplay(gameStartDisplay(table, start));
    }
    if (showsRoundResult(table, paging.overGameEnd) && table.roundEndResult) {
        return RoundEndDisplay({
            controls: paging.controls,
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
    const display = gameEndDisplay(table, end.viewerSeat);
    return display === null ? undefined : GameEndDisplay(display, end.actions);
}
