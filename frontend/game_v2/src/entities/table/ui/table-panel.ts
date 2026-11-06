import { type TemplateResult } from "lit-html";

import { type TablePanel } from "@/entities/table/lib/table-panel";
import { assertNever } from "@/shared/lib";

import { GameEndDisplay } from "./game-end-display";
import { GameStartDisplay } from "./game-start-display";
import { type PanelAction } from "./panel-actions";
import { RoundEndDisplay } from "./round-end-display";

/**
 * What the view adds to the table's panel: the seating's ways on (a replay's start) or its controls (the live opening
 * screen's OK), a round result's controls at its foot (the live confirm) and its paging, and the game end's ways on.
 */
export interface TablePanelControls {
    readonly seatingActions?: readonly PanelAction[];
    readonly seatingControls?: TemplateResult;
    readonly resultControls?: TemplateResult;
    readonly onPage?: (page: number) => void;
    readonly endActions?: readonly PanelAction[];
}

/** The table's own panel over the board, as `tablePanel` mapped it, with the view's controls. */
export function TablePanelDisplay(
    panel: TablePanel,
    controls: TablePanelControls = {},
): TemplateResult {
    switch (panel.kind) {
        case "seating": {
            return GameStartDisplay(
                panel.display,
                controls.seatingActions,
                controls.seatingControls,
            );
        }
        case "result": {
            return RoundEndDisplay({
                controls: controls.resultControls,
                display: panel.display,
                onPage: controls.onPage,
            });
        }
        case "game_end": {
            return GameEndDisplay(panel.display, controls.endActions ?? []);
        }
        default: {
            return assertNever(panel);
        }
    }
}
