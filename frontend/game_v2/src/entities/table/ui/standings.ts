import "@/styles/standings.scss";
import { type TemplateResult } from "lit-html";

import { standingsDisplay } from "@/entities/table/lib/standings-display";
import { type TableState } from "@/entities/table/model/types";

import { type StandingsView } from "./board-overlay";
import { StandingsPanel } from "./standings-panel";

/**
 * The final standings of an ended table as the view shows them, its stylesheet with it: the module the views load
 * lazily (`loadStandingsRenderer`), so the game's first paint does without the panel, its mapper and its styles.
 */
export function renderStandings(
    table: TableState,
    view: StandingsView,
): TemplateResult | undefined {
    const display = standingsDisplay(table, view.viewerSeat);
    if (display === null) {
        return undefined;
    }
    return StandingsPanel({ actions: view.actions, display, onRound: view.onRound });
}
