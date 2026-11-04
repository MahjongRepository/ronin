import { type GameEndDisplayState, gameEndDisplay } from "@/entities/table/lib/game-end-display";
import {
    type GameStartDisplayState,
    gameStartDisplay,
    replaySeatingDisplay,
} from "@/entities/table/lib/game-start-display";
import { type RoundEndDisplayState, roundEndDisplay } from "@/entities/table/lib/round-end-display";
import { type BoardCallouts } from "@/entities/table/model/board-types";
import { type TableState } from "@/entities/table/model/types";

/**
 * The table's own panel over its board: the seating before the first deal, a round's result at a page (`afterCall`:
 * it waits until the win's call shown with it has been seen), or the game's end.
 */
export type TablePanel =
    | { readonly kind: "seating"; readonly display: GameStartDisplayState }
    | {
          readonly kind: "result";
          readonly display: RoundEndDisplayState;
          readonly afterCall: boolean;
      }
    | { readonly kind: "game_end"; readonly display: GameEndDisplayState };

/** How a view reads the table's panel: from whose seat, at which result page, and with which calls showing. */
export interface TablePanelView {
    /** The viewer's seat, which the seating and the game's end mark; null in a replay. */
    readonly viewerSeat: number | null;
    /** The whole seconds left of the game start pause the seating counts down; null when unknown. */
    readonly firstDealSeconds: number | null;
    /** The page of a round's result shown; one out of range shows the nearest. */
    readonly page: number;
    /** The game's last result still shows over the game's end (the live game's, until the player dismisses it). */
    readonly overGameEnd: boolean;
    readonly callouts: BoardCallouts | null;
}

/** Whether the calls shown are a win's (ron, tsumo), whose result panel waits until they have been seen. */
function callsAWin(callouts: BoardCallouts | null): boolean {
    return callouts?.items.some((item) => item.kind === "ron" || item.kind === "tsumo") ?? false;
}

function resultPanel(table: TableState, view: TablePanelView): TablePanel | null {
    const shown =
        table.phase === "round_ended" || (table.phase === "game_ended" && view.overGameEnd);
    if (!shown || table.roundEndResult === null) {
        return null;
    }
    return {
        afterCall: callsAWin(view.callouts),
        display: roundEndDisplay(
            { players: table.players, result: table.roundEndResult },
            view.page,
            table.hasAkadora,
        ),
        kind: "result",
    };
}

/**
 * The panel a table shows over its board: the seating once the game starts, until its first deal; the round's result
 * once it ends; the game's end once the game does, unless the view still shows the last round's result over it. Null
 * while a round plays.
 */
export function tablePanel(table: TableState, view: TablePanelView): TablePanel | null {
    if (table.phase === "pre_game" && table.players.length > 0) {
        const start = { secondsLeft: view.firstDealSeconds, viewerSeat: view.viewerSeat };
        return { display: gameStartDisplay(table, start), kind: "seating" };
    }
    const result = resultPanel(table, view);
    if (result !== null) {
        return result;
    }
    const end = gameEndDisplay(table, view.viewerSeat);
    return end === null ? null : { display: end, kind: "game_end" };
}

/** The seating a replay opens on, from its table as the game started: the starting scores, no seat the reader's. */
export function replaySeatingPanel(startTable: TableState): TablePanel {
    return { display: replaySeatingDisplay(startTable), kind: "seating" };
}
