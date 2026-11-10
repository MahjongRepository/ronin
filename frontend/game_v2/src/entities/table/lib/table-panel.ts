import { type GameEndDisplayState, gameEndDisplay } from "@/entities/table/lib/game-end-display";
import {
    type GameStartDisplayState,
    replaySeatingDisplay,
    tableSeatingDisplay,
} from "@/entities/table/lib/game-start-display";
import { type RoundEndDisplayState, roundEndDisplay } from "@/entities/table/lib/round-end-display";
import { type TableState } from "@/entities/table/model/types";

/**
 * A panel over the table's board: the seating (a live game's opening screen, a replay's start), a round's result at a page (`held`:
 * it opens after a pause, so the move that ended the round and its call are seen first), or the game's end.
 */
export type TablePanel =
    | { readonly kind: "seating"; readonly display: GameStartDisplayState }
    | {
          readonly kind: "result";
          readonly display: RoundEndDisplayState;
          readonly held: boolean;
      }
    | { readonly kind: "game_end"; readonly display: GameEndDisplayState };

/** How a view reads the table's panel: from whose seat, at which result page, and whether a result opens after a pause. */
export interface TablePanelView {
    /** The viewer's seat, which the game's end marks; null in a replay. */
    readonly viewerSeat: number | null;
    /** The page of a round's result shown; one out of range shows the nearest. */
    readonly page: number;
    /** The game's last result still shows over the game's end (the live game's, until the player dismisses it). */
    readonly overGameEnd: boolean;
    /** The round's result waits before it opens, so the move that ended the round has been seen. */
    readonly holdsResult: boolean;
}

function resultPanel(table: TableState, view: TablePanelView): TablePanel | null {
    const shown =
        table.phase === "round_ended" || (table.phase === "game_ended" && view.overGameEnd);
    if (!shown || table.roundEndResult === null) {
        return null;
    }
    return {
        display: roundEndDisplay(
            { players: table.players, result: table.roundEndResult },
            view.page,
            table.hasAkadora,
        ),
        held: view.holdsResult,
        kind: "result",
    };
}

/**
 * The panel a table shows over its board: the round's result once it ends; the game's end once the game does, unless
 * the view still shows the last round's result over it. Null before the first deal and while a round plays.
 */
export function tablePanel(table: TableState, view: TablePanelView): TablePanel | null {
    const result = resultPanel(table, view);
    if (result !== null) {
        return result;
    }
    const end = gameEndDisplay(table, view.viewerSeat);
    return end === null ? null : { display: end, kind: "game_end" };
}

/** The seating of the round on a dealt live table from the viewer's seat, the live game's opening screen. */
export function tableSeatingPanel(table: TableState, viewerSeat: number | null): TablePanel {
    return { display: tableSeatingDisplay(table, viewerSeat), kind: "seating" };
}

/**
 * The seating a replay opens on, from its table as the game started: the starting scores, no seat the reader's, the
 * seat its board is seen from marked.
 */
export function replaySeatingPanel(startTable: TableState, viewpointSeat: number): TablePanel {
    return { display: replaySeatingDisplay(startTable, viewpointSeat), kind: "seating" };
}
