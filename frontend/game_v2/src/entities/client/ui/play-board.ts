import { type TemplateResult, html, nothing } from "lit-html";

import { type DecisionCountdown } from "@/entities/client/model/countdown";
import {
    type PlayAction,
    type PlayCommand,
    type PlayDisplay,
} from "@/entities/client/model/play-display";
import { GameBoard } from "@/entities/table";
import { Tile } from "@/entities/tile";

import { countdownAnnouncement } from "./rotate-panel";

export interface PlayBoardProps {
    readonly display: PlayDisplay;
    readonly overlay?: TemplateResult;
    readonly onCommand: (command: PlayCommand) => void;
}

function CountdownView(countdown: DecisionCountdown | null): TemplateResult | typeof nothing {
    if (countdown?.kind === "running") {
        return html`<span class="decision-controls__countdown" title="Seconds left"
            >${countdown.secondsLeft}</span
        >`;
    }
    if (countdown?.kind === "expired") {
        return html`<span class="decision-controls__countdown decision-controls__countdown--expired"
            >Time up</span
        >`;
    }
    return nothing;
}

function isPass(action: PlayAction): boolean {
    return action.command.kind === "intent" && action.command.intent.type === "pass";
}

function ActionButton(action: PlayAction, onCommand: PlayBoardProps["onCommand"]): TemplateResult {
    return html`<button
        type="button"
        class="decision-controls__action ${isPass(action) ? "secondary" : ""}"
        aria-label=${[action.label, ...action.tiles].join(" ")}
        aria-pressed=${action.pressed === null ? nothing : String(action.pressed)}
        @click=${() => onCommand(action.command)}
    >
        <span class="decision-controls__label">${action.label}</span>${
            action.tiles.length === 0
                ? nothing
                : html`<span class="decision-controls__tiles">${action.tiles.map(
                      (face) =>
                          html`<span class="decision-controls__tile">${Tile(face, "face")}</span>`,
                  )}</span>`
        }
    </button>`;
}

/**
 * The decision's corner of the board: the countdown read from the state's logical time, the seat's furiten, and a
 * button per thing the decision takes besides a tile. Only the countdown's thresholds are announced.
 */
function DecisionControls(
    display: PlayDisplay,
    onCommand: PlayBoardProps["onCommand"],
): TemplateResult | undefined {
    const { actions, countdown, furiten } = display;
    if (actions.length === 0 && countdown === null && !furiten) {
        return undefined;
    }
    const status =
        countdown === null && !furiten
            ? nothing
            : html`<div class="decision-controls__status">${CountdownView(countdown)}${
                  furiten ? html`<span class="decision-controls__furiten">Furiten</span>` : nothing
              }</div>`;
    const buttons =
        actions.length === 0
            ? nothing
            : html`<div class="decision-controls__actions">${actions.map((action) =>
                  ActionButton(action, onCommand),
              )}</div>`;
    return html`<div class="decision-controls">
        ${status}${buttons}
        <span class="decision-controls__announce" aria-live="polite">${countdownAnnouncement(countdown)}</span>
    </div>`;
}

/**
 * The live board: the table from the viewer's seat with its decision's controls in their corner. A tap on one of the
 * viewer's tiles sends the intent the display gives it, and a tile with none sends nothing.
 */
export function PlayBoard({ display, onCommand, overlay }: PlayBoardProps): TemplateResult {
    function onTile(tileId: number): void {
        const intent = display.tileIntents.get(tileId);
        if (intent !== undefined) {
            onCommand({ intent, kind: "intent" });
        }
    }
    return GameBoard({
        actions: DecisionControls(display, onCommand),
        debug: false,
        localHand: { onTile, tileAction: display.tileAction },
        overlay,
        state: display.board,
    });
}
