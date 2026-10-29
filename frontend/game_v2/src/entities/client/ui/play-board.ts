import { type TemplateResult, html, nothing } from "lit-html";

import { type DecisionCountdown } from "@/entities/client/model/countdown";
import {
    type PlayAction,
    type PlayCommand,
    type PlayDisplay,
    type PlayNotice,
    type ResultControls,
} from "@/entities/client/model/play-display";
import { type BoardNotice, GameBoard, type TableState, boardOverlay } from "@/entities/table";
import { Tile } from "@/entities/tile";

import { countdownAnnouncement } from "./rotate-panel";
import { FailurePanel, LeaveConfirm } from "./session-panels";

export interface PlayBoardProps {
    readonly display: PlayDisplay;
    /** The table the display was mapped from, whose panel (seating, result, standings) shows over the board. */
    readonly table: TableState;
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

/** The time left to the round advance, as words on the panel itself, since a touch screen shows no tooltip. */
function ResultTime(countdown: DecisionCountdown | null): TemplateResult | typeof nothing {
    if (countdown?.kind === "running") {
        return html`<span class="round-end-result__countdown">${countdown.secondsLeft}s left</span>`;
    }
    if (countdown?.kind === "expired") {
        return html`<span class="round-end-result__countdown round-end-result__countdown--expired"
            >Time up</span
        >`;
    }
    return nothing;
}

/**
 * The round result's controls at the panel's foot, beside the scores: its primary button with the time left to the
 * round advance under its label, or, once the seat confirmed, that it waits for the others with the time still
 * counting down. Only the countdown's thresholds are announced.
 */
function ResultControlsView(
    result: ResultControls | null,
    onCommand: PlayBoardProps["onCommand"],
): TemplateResult | undefined {
    if (result === null) {
        return undefined;
    }
    const { action, countdown, waiting } = result;
    const control =
        action === null
            ? html`<span class="round-end-result__wait">
                  ${waiting ? html`<span class="round-end-result__waiting">Waiting for others</span>` : nothing}
                  ${ResultTime(countdown)}
              </span>`
            : html`<button
                  type="button"
                  class="round-end-result__confirm"
                  aria-label=${action.label}
                  @click=${() => onCommand(action.command)}
              >
                  <span class="round-end-result__confirm-label">${action.label}</span>
                  ${ResultTime(countdown)}
              </button>`;
    return html`<span class="round-end-result__controls">
        ${control}
        <span class="round-end-result__announce" aria-live="polite">${countdownAnnouncement(countdown)}</span>
    </span>`;
}

/**
 * The panel over the board: an end that blocks it, else the question leaving mid-game asks, else the table's own
 * (seating, a result, the standings).
 */
function PlayOverlay(
    display: PlayDisplay,
    table: TableState,
    onCommand: PlayBoardProps["onCommand"],
): TemplateResult | undefined {
    if (display.failure !== null) {
        return FailurePanel(display.failure, onCommand);
    }
    if (display.leave.confirming) {
        return LeaveConfirm(onCommand);
    }
    return boardOverlay(table, {
        controls: ResultControlsView(display.result, onCommand),
        onPage: (page) => onCommand({ kind: "show_result_page", page }),
        overStandings: display.resultOverStandings,
        page: display.resultPage,
    });
}

function boardNotice(notice: PlayNotice, onCommand: PlayBoardProps["onCommand"]): BoardNotice {
    const { action, text, tone } = notice;
    if (action === undefined) {
        return { text, tone };
    }
    return {
        action: { label: action.label, onClick: () => onCommand(action.command) },
        text,
        tone,
    };
}

/**
 * The live board: the table from the viewer's seat with its decision's controls in their corner, its notices over the
 * table, and a panel over it: an end that blocks the board, the leave question, or the table's own, a round's result
 * at the page the display picked with its controls, or the game's last result over the standings until the player
 * dismisses it. A tap on one of the viewer's tiles sends the intent the display gives it, and a tile with none sends
 * nothing; turning the result's page is a command too. While an end or the leave question blocks the board, the board
 * under it is inert.
 */
export function PlayBoard({ display, onCommand, table }: PlayBoardProps): TemplateResult {
    function onTile(tileId: number): void {
        const intent = display.tileIntents.get(tileId);
        if (intent !== undefined) {
            onCommand({ intent, kind: "intent" });
        }
    }
    return GameBoard({
        actions: DecisionControls(display, onCommand),
        debug: false,
        inert: display.failure !== null || display.leave.confirming,
        localHand: { onTile, tileAction: display.tileAction },
        notices: display.notices.map((notice) => boardNotice(notice, onCommand)),
        overlay: PlayOverlay(display, table, onCommand),
        scoreDiff: {
            onPin: (seat) => onCommand({ kind: "pin_nameplate", seat }),
            pinned: display.pinnedNameplate,
        },
        state: display.board,
    });
}
