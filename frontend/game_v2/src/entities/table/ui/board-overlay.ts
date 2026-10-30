import { type TemplateResult } from "lit-html";

import { roundEndDisplay } from "@/entities/table/lib/round-end-display";
import { type TableState } from "@/entities/table/model/types";
import { type RetryingLoad, type RetryingLoadDeps, startRetryingLoad } from "@/shared/lib";

import { GameStartDisplay } from "./game-start-display";
import { RoundEndDisplay } from "./round-end-display";
import { type StandingsAction } from "./standings-panel";

/**
 * The page of a round's result the view shows, and its way to change it; without it the first page shows. A page out
 * of range shows the nearest. The live game adds its controls to the result's head (its confirm), and shows the
 * game's last result over the standings until the player dismisses it.
 */
export interface ResultPaging {
    readonly page: number;
    readonly onPage?: (page: number) => void;
    readonly controls?: TemplateResult;
    readonly overStandings?: boolean;
}

/** Draws the final standings of an ended table as the view asks; the lazily loaded `renderStandings`. */
export type StandingsRenderer = (
    table: TableState,
    view: StandingsView,
) => TemplateResult | undefined;

/**
 * How the view shows the final standings: the seat they are read from (the live player's, the replay's bottom seat),
 * its ways on, given `onRound`, how a ledger row shows its round's result, and the renderer once the view loaded it.
 */
export interface StandingsView {
    readonly viewerSeat: number | null;
    readonly actions: readonly StandingsAction[];
    readonly onRound?: (round: number) => void;
    readonly renderer: StandingsRenderer | null;
}

const NO_STANDINGS_VIEW: StandingsView = { actions: [], renderer: null, viewerSeat: null };

async function loadStandingsRenderer(): Promise<StandingsRenderer> {
    const { renderStandings } = await import("./standings");
    return renderStandings;
}

/**
 * Start loading the standings' panel, mapper and stylesheet, a chunk of their own, with retries; each view that may
 * show them starts it as it mounts.
 */
export function startStandingsLoad(
    deps: Omit<RetryingLoadDeps<StandingsRenderer>, "load">,
): RetryingLoad<StandingsRenderer> {
    return startRetryingLoad({ ...deps, load: loadStandingsRenderer });
}

/**
 * The panel a table shows over its board: the seating once the game starts, until its first deal; the round's
 * result once it ends, at the page the view picked; the standings once the game does, unless the view still shows
 * the last round's result over them, and only once the view holds the standings' renderer.
 */
export function boardOverlay(
    table: TableState,
    paging: ResultPaging = { page: 0 },
    standings: StandingsView = NO_STANDINGS_VIEW,
): TemplateResult | undefined {
    if (table.phase === "pre_game" && table.players.length > 0) {
        return GameStartDisplay(table.players, table.firstDealerSeat);
    }
    const resultShows =
        table.phase === "round_ended" ||
        (table.phase === "game_ended" && paging.overStandings === true);
    if (resultShows && table.roundEndResult) {
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
    return standings.renderer?.(table, standings);
}
