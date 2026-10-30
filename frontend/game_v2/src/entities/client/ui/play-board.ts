import { type TemplateResult, html, nothing } from "lit-html";

import { type DecisionCountdown } from "@/entities/client/model/countdown";
import {
    type PlayAction,
    type PlayCommand,
    type PlayDisplay,
    type PlayNotice,
    type ResultControls,
} from "@/entities/client/model/play-display";
import { type SessionStatusDisplay } from "@/entities/session";
import {
    type BoardNotice,
    GameBoard,
    type StandingsAction,
    type StandingsRenderer,
    type TableState,
    boardOverlay,
} from "@/entities/table";
import { Tile } from "@/entities/tile";

import { GameMenu } from "./game-menu";
import { countdownAnnouncement } from "./rotate-panel";
import { FailurePanel, LeaveConfirm } from "./session-panels";

/** Where the standings lead the player once the game ends: this game's replay and the game history. */
export interface StandingsLinks {
    readonly replay: string;
    readonly history: string;
}

export interface PlayBoardProps {
    readonly display: PlayDisplay;
    /** The table the display was mapped from, whose panel (seating, result, standings) shows over the board. */
    readonly table: TableState;
    readonly onCommand: (command: PlayCommand) => void;
    /** The session's status, which the board's corner shows beside the way back; none on a board with no session. */
    readonly status?: SessionStatusDisplay;
    /** What the page adds to the corner before the status (the debug log). */
    readonly menuExtra?: TemplateResult;
    /** The standings' links; without them the standings offer only the game's last result and the way back. */
    readonly links?: StandingsLinks;
    /** What draws the final standings once the view loaded it; until then the ended game shows no panel. */
    readonly standings: StandingsRenderer | null;
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

function commandAction(
    action: PlayAction,
    onCommand: PlayBoardProps["onCommand"],
): StandingsAction {
    return { kind: "button", label: action.label, onClick: () => onCommand(action.command) };
}

/**
 * The standings' ways on: back to the game's last result while it can reopen, this game's replay, the game history,
 * and the lobby, the primary one.
 */
function standingsActions(
    display: PlayDisplay,
    links: StandingsLinks | undefined,
    onCommand: PlayBoardProps["onCommand"],
): StandingsAction[] {
    const actions: StandingsAction[] = [];
    if (display.lastResult !== null) {
        actions.push(commandAction(display.lastResult, onCommand));
    }
    if (links !== undefined) {
        actions.push(
            { href: links.replay, kind: "link", label: "Replay" },
            { href: links.history, kind: "link", label: "Game history" },
        );
    }
    actions.push({
        kind: "button",
        label: "Lobby",
        onClick: () => onCommand(display.leave.command),
        primary: true,
    });
    return actions;
}

/**
 * The panel over the board: an end that blocks it, else the question leaving mid-game asks, else the table's own
 * (seating, a result, the standings from the viewer's seat).
 */
function PlayOverlay({
    display,
    links,
    onCommand,
    standings,
    table,
}: PlayBoardProps): TemplateResult | undefined {
    if (display.failure !== null) {
        return FailurePanel(display.failure, onCommand);
    }
    if (display.leave.confirming) {
        return LeaveConfirm(onCommand);
    }
    return boardOverlay(
        table,
        {
            controls: ResultControlsView(display.result, onCommand),
            onPage: (page) => onCommand({ kind: "show_result_page", page }),
            overStandings: display.resultOverStandings,
            page: display.resultPage,
        },
        {
            actions: standingsActions(display, links, onCommand),
            renderer: standings,
            viewerSeat: display.viewerSeat,
        },
    );
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
export function PlayBoard(props: PlayBoardProps): TemplateResult {
    const { display, menuExtra, onCommand, status } = props;
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
        menu:
            status === undefined
                ? undefined
                : GameMenu({ extra: menuExtra, leave: display.leave, onCommand, status }),
        notices: display.notices.map((notice) => boardNotice(notice, onCommand)),
        overlay: PlayOverlay(props),
        scoreDiff: {
            onPin: (seat) => onCommand({ kind: "pin_nameplate", seat }),
            pinned: display.pinnedNameplate,
        },
        state: display.board,
    });
}
