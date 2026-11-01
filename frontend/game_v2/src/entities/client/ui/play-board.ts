import { type TemplateResult, html, nothing } from "lit-html";
import { repeat } from "lit-html/directives/repeat.js";

import { type NoticeSheetDisplay, type PlayNotice } from "@/entities/client/model/board-notices";
import { type DecisionCountdown } from "@/entities/client/model/countdown";
import {
    countdownAnnouncement,
    expiryNote,
    moveName,
} from "@/entities/client/model/countdown-text";
import {
    type DecisionAction,
    type DecisionStanding,
} from "@/entities/client/model/decision-controls";
import {
    type PlayDisplay,
    type PlayPanel,
    type SwitchControl,
} from "@/entities/client/model/play-display";
import {
    type EscapeStep,
    type PlayAction,
    type PlayCommand,
    commandFocusKey,
    escapeFocusKey,
} from "@/entities/client/model/play-ui";
import { type ResultControls } from "@/entities/client/model/result-controls";
import {
    type BoardNotice,
    DECISION_ACTION_FOCUS_KEY,
    GameBoard,
    NoticeSheet,
    PANEL_CONTROL_FOCUS_KEY,
    type PanelAction,
    TablePanelDisplay,
} from "@/entities/table";
import { Meld, Tile } from "@/entities/tile";
import { assertNever, focusByKey, focusKeys } from "@/shared/lib";

import { GameMenu } from "./game-menu";
import { FailurePanel, LeaveConfirm } from "./session-panels";

/** Where the game's end leads the player: this game's replay and the game history. */
export interface GameEndLinks {
    readonly replay: string;
    readonly history: string;
}

export interface PlayBoardProps {
    readonly display: PlayDisplay;
    readonly onCommand: (command: PlayCommand) => void;
    /** What the page adds to the corner before the status (the debug log). */
    readonly menuExtra?: TemplateResult;
    /** The game end's links; without them it offers only the game's last result and the way back. */
    readonly links?: GameEndLinks;
}

/** What the timer's caption line says over its digits: that time ran out, the answer went, or the bank alone drains. */
function timerCaption(
    standing: DecisionStanding | null,
    countdown: DecisionCountdown | null,
): string {
    if (standing === "submitted") {
        return "Sent";
    }
    if (countdown?.kind === "expired") {
        return "Time up";
    }
    return countdown?.kind === "running" && countdown.turn?.inBank === true ? "Bank" : "";
}

/**
 * The digits: the base time and the bank apart (`5 +20`) on a turn, the bank marked once it alone drains; a call's
 * seconds; 0 once time ran out; none once answered.
 */
function TimerDigits(countdown: DecisionCountdown | null): TemplateResult | typeof nothing {
    if (countdown?.kind === "expired") {
        return html`<span class="decision-controls__countdown decision-controls__countdown--expired">0</span>`;
    }
    if (countdown?.kind !== "running") {
        return nothing;
    }
    const { turn } = countdown;
    if (turn === null) {
        return html`<span class="decision-controls__countdown" title="Seconds left">${countdown.secondsLeft}</span>`;
    }
    const bankClass = turn.inBank
        ? "decision-controls__bank decision-controls__bank--draining"
        : "decision-controls__bank";
    const title = turn.inBank
        ? "Seconds left in your time bank"
        : "Seconds left, then your time bank";
    return html`<span class="decision-controls__countdown ${turn.inBank ? "decision-controls__countdown--spent" : ""}" title=${title}
            >${turn.baseSeconds}</span
        ><span class=${bankClass} title=${title}>+${turn.bankSeconds}</span>`;
}

/**
 * The timer's slot, fixed in size and place whatever it shows, so running out, answering and the bank never move it
 * or the controls: a caption line over the digits.
 */
function DecisionTimer(display: DecisionView): TemplateResult {
    const { countdown, decisionStanding } = display;
    const caption = timerCaption(decisionStanding, countdown);
    const digits = decisionStanding === "submitted" ? nothing : TimerDigits(countdown);
    return html`<div class="decision-timer ${caption === "" ? "" : `decision-timer--${caption.toLowerCase().replace(" ", "-")}`}">
        <span class="decision-timer__caption">${caption}</span>
        <span class="decision-timer__digits">${digits}</span>
    </div>`;
}

function rankClass(action: DecisionAction): string {
    const choice = action.group === null ? "" : " decision-controls__action--choice";
    const step = opensTileChoice(action) ? " decision-controls__action--step" : "";
    return `decision-controls__action--${action.rank}${choice}${step}`;
}

/** The tiles a control shows: a second step's group as its meld will lie, or a first step's preview faces. */
function ActionTiles(action: DecisionAction): TemplateResult | typeof nothing {
    if (action.group !== null) {
        return html`<span class="decision-controls__group">${Meld(action.group)}</span>`;
    }
    if (action.tiles.length === 0) {
        return nothing;
    }
    return html`<span class="decision-controls__tiles">${action.tiles.map(
        (face) => html`<span class="decision-controls__tile">${Tile(face, "face")}</span>`,
    )}</span>`;
}

/** The riichi toggle's lamp, so its on state reads by more than its colour: a box, checked while on. */
function Lamp(pressed: boolean | null): TemplateResult {
    return html`<span class="decision-controls__lamp ${pressed ? "decision-controls__lamp--on" : ""}" aria-hidden="true"></span>`;
}

/**
 * A decision control: its label (a second step's choice shows its tiles in its place), riichi's lamp, Back's arrow;
 * once answered, inert, the one that sent the answer marked.
 */
function ActionButton(
    action: DecisionAction,
    answered: boolean,
    onCommand: PlayBoardProps["onCommand"],
): TemplateResult {
    const isBack = action.command.kind === "step_back";
    const label =
        action.group === null
            ? html`<span class="decision-controls__label">${isBack ? html`<span aria-hidden="true">← </span>` : nothing}${action.label}</span>`
            : nothing;
    const lamp = action.command.kind === "toggle_riichi_pick" ? Lamp(action.pressed) : nothing;
    return html`<button
        type="button"
        class="decision-controls__action ${rankClass(action)} ${action.chosen ? "decision-controls__action--chosen" : ""}"
        aria-label=${[action.label, ...action.tiles, ...(action.chosen ? ["(sent)"] : [])].join(" ")}
        aria-pressed=${action.pressed === null ? nothing : String(action.pressed)}
        aria-disabled=${answered ? "true" : nothing}
        data-focus-key=${focusKeys(commandFocusKey(action.command), answered ? null : DECISION_ACTION_FOCUS_KEY) ?? nothing}
        @click=${() => {
            if (!answered) {
                onCommand(action.command);
            }
        }}
    >
        ${lamp}${label}${ActionTiles(action)}
    </button>`;
}

/** A control's identity across renders, so a focused one keeps its element when a step opens or closes around it. */
function actionKey(action: DecisionAction): string {
    return JSON.stringify(action.command);
}

/** Whether a control opens or closes a call's choice of tiles, which the second step keeps in the column. */
function opensTileChoice(action: DecisionAction): boolean {
    return action.command.kind === "toggle_tile_choice";
}

/**
 * Which control takes the foreground band beside the timer on a phone: the lowest-ranked (the riichi toggle among
 * them), unless it is a win, a choice of tiles or a call's first step, which rise with the rest, so opening a choice
 * never moves its control.
 */
function bandAction(actions: readonly DecisionAction[]): DecisionAction | null {
    const last = actions.at(-1);
    if (last === undefined) {
        return null;
    }
    const rises = last.rank === "win" || last.group !== null || opensTileChoice(last);
    return rises ? null : last;
}

/** What the decision's controls draw: its controls, its countdown and where it stands. */
export type DecisionView = Pick<PlayDisplay, "actions" | "countdown" | "decisionStanding">;

/**
 * The decision's controls by the hand, ranked, with the timer's slot after them: a desktop lays them in one row ending
 * at the hand's right end; a phone keeps the lowest-ranked in the band beside the timer and stacks the rest above it,
 * pairing them when the column is too short. They stay in place while the decision is open, expired or answered.
 * Only the countdown's thresholds and its bank are announced.
 */
export function DecisionControls(
    display: DecisionView,
    onCommand: PlayBoardProps["onCommand"],
): TemplateResult | undefined {
    const { actions, countdown, decisionStanding } = display;
    if (decisionStanding === null) {
        return undefined;
    }
    const answered = decisionStanding === "submitted";
    const band = bandAction(actions);
    const upper = band === null ? actions : actions.slice(0, -1);
    return html`<div
        class="decision-controls decision-controls--${decisionStanding}"
        data-upper=${upper.length}
    >
        <div class="decision-controls__upper">${repeat(upper, actionKey, (action) => ActionButton(action, answered, onCommand))}</div>
        <div class="decision-controls__band">
            ${band === null ? nothing : ActionButton(band, answered, onCommand)}${DecisionTimer(display)}
        </div>
        <span class="decision-controls__announce" aria-live="polite">${countdownAnnouncement(countdown)}</span>
    </div>`;
}

/**
 * A play switch: a native button (focus, Enter and Space) with the switch role, shown as its letter, named by its label
 * (hidden but read, and its tooltip), its state told by the chip's fill and a lamp under the letter (a bar while on, a
 * ring while off), never by colour alone.
 */
function SwitchButton(
    control: SwitchControl,
    onCommand: PlayBoardProps["onCommand"],
): TemplateResult {
    return html`<button
        type="button"
        role="switch"
        class="play-switch ${control.on ? "play-switch--on" : ""}"
        aria-checked=${String(control.on)}
        title=${control.label}
        @click=${() => onCommand(control.command)}
    >
        <span class="play-switch__letter" aria-hidden="true">${control.letter}</span
        ><span class="play-switch__lamp" aria-hidden="true"></span
        ><span class="play-switch__label">${control.label}</span>
    </button>`;
}

/** What each letter stands for, over the switches while the player keeps it open. */
function SwitchNames(switches: readonly SwitchControl[]): TemplateResult {
    return html`<ul class="play-switches__names" aria-hidden="true">
        ${switches.map(
            (control) =>
                html`<li>
                    <span class="play-switches__names-letter">${control.letter}</span
                    ><span>${control.label}</span>
                </li>`,
        )}
    </ul>`;
}

/**
 * The play switches in their slot on the band as a strip of letters, Mahjong Soul's, its last button showing or hiding
 * their names; none while the player may not turn them.
 */
export function PlaySwitches(
    switches: readonly SwitchControl[],
    namesShown: boolean,
    onCommand: PlayBoardProps["onCommand"],
): TemplateResult | undefined {
    if (switches.length === 0) {
        return undefined;
    }
    return html`<div class="play-switches" role="group" aria-label="Play switches">
        ${repeat(
            switches,
            (control) => control.playSwitch,
            (control) => SwitchButton(control, onCommand),
        )}<button
            type="button"
            class="play-switches__names-toggle"
            aria-pressed=${String(namesShown)}
            aria-label="Switch names"
            title=${namesShown ? "Hide switch names" : "Show switch names"}
            @click=${() => onCommand({ kind: "toggle_switch_names" })}
        >
            <svg class="play-switches__arrow" viewBox="0 0 10 10" aria-hidden="true">
                <polygon points=${namesShown ? "7,1 7,9 2,5" : "3,1 3,9 8,5"}></polygon>
            </svg>
        </button>
        ${namesShown ? SwitchNames(switches) : nothing}
    </div>`;
}

/**
 * Step back on Escape; when the focus was on a decision control, it moves to the toggle that opened the step, found
 * by the key the display names for it, so the focus never falls out of the board.
 */
function stepBack(
    board: HTMLElement,
    escape: EscapeStep,
    onCommand: PlayBoardProps["onCommand"],
): void {
    const focused = board.ownerDocument.activeElement;
    const inControls =
        focused instanceof Element &&
        board.contains(focused) &&
        focused.closest(".decision-controls") !== null;
    onCommand(escape.command);
    if (inControls) {
        focusByKey(board, escapeFocusKey(escape));
    }
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
                  data-focus-key=${PANEL_CONTROL_FOCUS_KEY}
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

function commandAction(action: PlayAction, onCommand: PlayBoardProps["onCommand"]): PanelAction {
    return { kind: "button", label: action.label, onClick: () => onCommand(action.command) };
}

/**
 * The game end's ways on: back to the game's last result while it can reopen, this game's replay, the game history,
 * and the lobby, the primary one.
 */
function gameEndActions(
    display: PlayDisplay,
    links: GameEndLinks | undefined,
    onCommand: PlayBoardProps["onCommand"],
): PanelAction[] {
    const actions: PanelAction[] = [];
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

const CLOSE_NOTICE: PlayCommand = { kind: "close_notice" };

/** What goes on beneath a notice's sheet: play, and the decision or round confirm the player owes with its seconds. */
function owedMove(countdown: NoticeSheetDisplay["countdown"]): TemplateResult | typeof nothing {
    if (countdown?.kind === "running") {
        return html` ${moveName(countdown.move)}:
            <span class="notice-sheet__seconds">${countdown.secondsLeft}</span> s
            left${countdown.turn?.inBank === true ? " in your time bank" : ""}.`;
    }
    if (countdown?.kind === "expired") {
        return html` ${moveName(countdown.move)}, and its time is up: ${expiryNote(countdown.move)}.`;
    }
    return nothing;
}

function SheetNote(countdown: NoticeSheetDisplay["countdown"]): TemplateResult {
    return html`<p class="notice-sheet__note">Play goes on beneath this sheet.${owedMove(countdown)}</p>
        <span class="notice-sheet__announce" aria-live="polite">${countdownAnnouncement(countdown)}</span>`;
}

/** The panel the display put over the board, drawn with its controls. */
function OverlayPanel(panel: PlayPanel, props: PlayBoardProps): TemplateResult {
    const { display, links, onCommand } = props;
    switch (panel.kind) {
        case "failure": {
            return FailurePanel(panel.failure, onCommand);
        }
        case "leave": {
            return LeaveConfirm(onCommand);
        }
        case "notice_sheet": {
            const { countdown, notices, opener } = panel.sheet;
            return NoticeSheet({
                note: SheetNote(countdown),
                notices: notices.map((notice) => boardNotice(notice, onCommand)),
                onClose: () => onCommand(CLOSE_NOTICE),
                openerId: opener,
            });
        }
        case "seating":
        case "result":
        case "game_end": {
            return TablePanelDisplay(panel, {
                endActions: gameEndActions(display, links, onCommand),
                onPage: (page) => onCommand({ kind: "show_result_page", page }),
                resultControls: ResultControlsView(display.result, onCommand),
            });
        }
        default: {
            return assertNever(panel);
        }
    }
}

/** A notice as the board draws it: found by its kind, opened whole by "Show all". */
function boardNotice(notice: PlayNotice, onCommand: PlayBoardProps["onCommand"]): BoardNotice {
    const { action, kind, text, tone } = notice;
    const shown = {
        id: kind,
        onShowAll: () => onCommand({ kind: "show_notice", notice: kind }),
        text,
        tone,
    };
    if (action === undefined) {
        return shown;
    }
    return { ...shown, action: { label: action.label, onClick: () => onCommand(action.command) } };
}

/**
 * The live board: the table from the viewer's seat with its decision's controls in their corner, its notices over the
 * table, and a panel over it: an end that blocks the board, the leave question, or the table's own, a round's result
 * at the page the display picked with its controls, or the game's last result over the game's end until the player
 * dismisses it. A tap on one of the viewer's tiles sends the intent the display gives it, and a tile with none sends
 * nothing; turning the result's page is a command too. While an end, the leave question or a notice's sheet blocks
 * the board, the board under it is inert. Each new showing of calls is read out once.
 */
export function PlayBoard(props: PlayBoardProps): TemplateResult {
    const { display, menuExtra, onCommand } = props;
    const { escape, overlay } = display;
    const inert = overlay?.blocksBoard ?? false;
    function onTile(tileId: number): void {
        const intent = display.tileIntents.get(tileId);
        if (intent !== undefined) {
            onCommand({ intent, kind: "intent" });
        }
    }
    return GameBoard({
        actions: DecisionControls(display, onCommand),
        announceCalls: true,
        callouts: display.callouts,
        debug: false,
        furiten: display.furiten,
        inert,
        localHand: { onTile, tileAction: display.tileAction },
        menu: GameMenu({
            extra: menuExtra,
            leave: display.leave,
            onCommand,
            status: display.status,
        }),
        notices: display.notices.map((notice) => boardNotice(notice, onCommand)),
        onEscape:
            escape === null || inert ? undefined : (board) => stepBack(board, escape, onCommand),
        overlay: overlay === null ? undefined : OverlayPanel(overlay.panel, props),
        overlayAfterCall: overlay?.panel.kind === "result" && overlay.panel.afterCall,
        platePress: {
            kind: "pin",
            onPin: (seat) => onCommand({ kind: "pin_nameplate", seat }),
            pinned: display.pinnedNameplate,
        },
        state: display.board,
        switches: PlaySwitches(display.switches, display.switchNames, onCommand),
    });
}
