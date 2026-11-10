import { type TemplateResult, html, nothing } from "lit-html";
import { repeat } from "lit-html/directives/repeat.js";

import { type NoticeSheetDisplay, type PlayNotice } from "@/entities/client/model/board-notices";
import { type DecisionCountdown } from "@/entities/client/model/countdown";
import {
    countdownAnnouncement,
    expiredSentence,
    moveName,
} from "@/entities/client/model/countdown-text";
import { type DecisionAction } from "@/entities/client/model/decision-controls";
import {
    type OpeningControls,
    type PlayDisplay,
    type PlayPanel,
    type SwitchControl,
} from "@/entities/client/model/play-display";
import {
    type PlayAction,
    type PlayCommand,
    commandFocusKey,
    intentCommand,
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
import { Tile, spokenTileName } from "@/entities/tile";
import { type Clock } from "@/shared/clock";
import { type Locale, type MessageKey, type WindScript, formatList, t } from "@/shared/i18n";
import { assertNever, focusKeys } from "@/shared/lib";
import { focusOnFirstRender } from "@/shared/ui";

import { ControlsHelp } from "./controls-help";
import { GameMenu } from "./game-menu";
import { playInput } from "./play-input";
import { withSecondsFigure } from "./seconds-figure";
import { FailurePanel, LeaveConfirm } from "./session-panels";

/** Where the game's end leads the player: this game's replay and the game history. */
export interface GameEndLinks {
    readonly replay: string;
    readonly history: string;
}

export interface PlayBoardProps {
    readonly display: PlayDisplay;
    readonly clock: Clock;
    readonly onCommand: (command: PlayCommand) => void;
    readonly onLanguage: (locale: Locale) => void;
    readonly onWinds: (script: WindScript) => void;
    readonly onTileLabels: (on: boolean) => void;
    /** What the page adds to the corner before the settings (the debug log). */
    readonly menuExtra?: TemplateResult;
    /** The game end's links; without them it offers only the game's last result and the way back. */
    readonly links?: GameEndLinks;
}

type TimerCaption = "time_up" | "bank";

const TIMER_CAPTIONS: Readonly<Record<TimerCaption, MessageKey>> = {
    bank: "game.timer.bank",
    time_up: "game.timer.time_up",
};

function timerCaption(countdown: DecisionCountdown | null): TimerCaption | null {
    if (countdown?.kind === "expired") {
        return "time_up";
    }
    return countdown?.kind === "running" && countdown.clock?.inBank === true ? "bank" : null;
}

/**
 * Show base time and bank apart (`5 +20`) on turns and calls, marking the bank once it alone drains; 0 once time
 * ran out; none once answered.
 */
function TimerDigits(countdown: DecisionCountdown | null): TemplateResult | typeof nothing {
    if (countdown?.kind === "expired") {
        return html`<span class="decision-controls__countdown decision-controls__countdown--expired">0</span>`;
    }
    if (countdown?.kind !== "running") {
        return nothing;
    }
    const { clock } = countdown;
    if (clock === null) {
        return html`<span class="decision-controls__countdown" title=${t("game.timer.seconds_left")}>${countdown.secondsLeft}</span>`;
    }
    const bankClass = clock.inBank
        ? "decision-controls__bank decision-controls__bank--draining"
        : "decision-controls__bank";
    const title = t(clock.inBank ? "game.timer.bank_seconds_left" : "game.timer.seconds_then_bank");
    return html`<span class="decision-controls__countdown ${clock.inBank ? "decision-controls__countdown--spent" : ""}" title=${title}
            >${clock.baseSeconds}</span
        ><span class=${bankClass} title=${title}>+${clock.bankSeconds}</span>`;
}

/**
 * The timer's slot, fixed in size and place while the decision is answerable: a caption line over the digits.
 */
function DecisionTimer(display: DecisionView): TemplateResult {
    const { countdown } = display;
    const caption = timerCaption(countdown);
    const digits = TimerDigits(countdown);
    return html`<div class="decision-timer ${caption === null ? "" : `decision-timer--${caption.replace("_", "-")}`}">
        <span class="decision-timer__caption">${caption === null ? "" : t(TIMER_CAPTIONS[caption])}</span>
        <span class="decision-timer__digits">${digits}</span>
    </div>`;
}

function kindClass(action: DecisionAction): string {
    return `decision-controls__action--${action.rank} decision-controls__action--${action.kind}`;
}

/** The hand's tiles a control shows after its label: a chi's pair, the tile of one kan among several. */
function ActionTiles(action: DecisionAction): TemplateResult | typeof nothing {
    if (action.tiles.length === 0) {
        return nothing;
    }
    return html`<span class="decision-controls__tiles">${action.tiles.map(
        (face) => html`<span class="decision-controls__tile">${Tile(face, "face")}</span>`,
    )}</span>`;
}

function offerLabel(action: DecisionAction): string {
    if (action.tiles.length === 0) {
        return action.label;
    }
    return `${action.label} ${formatList(action.tiles.map(spokenTileName))}`;
}

/** A decision control: its label, then the hand's tiles that tell it from another of its kind. */
function ActionButton(
    action: DecisionAction,
    onCommand: PlayBoardProps["onCommand"],
    keyHints: boolean,
): TemplateResult {
    const isPass = action.kind === "pass";
    return html`<button
        type="button"
        class="decision-controls__action ${kindClass(action)}"
        aria-label=${offerLabel(action)}
        aria-keyshortcuts=${actionKeys(action, isPass)}
        aria-pressed=${action.pressed === null ? nothing : String(action.pressed)}
        data-focus-key=${focusKeys(commandFocusKey(action.command), DECISION_ACTION_FOCUS_KEY) ?? nothing}
        @click=${() => onCommand(action.command)}
    >
        <span class="decision-controls__label">${action.label}</span>${ActionTiles(action)}${keyHints ? KeyCap(action, isPass) : nothing}
    </button>`;
}

/** A control's key as its cap shows it: Escape for a pass, else its digit; none for a control with neither. */
function KeyCap(action: DecisionAction, escapes: boolean): TemplateResult | typeof nothing {
    const keyName = escapes ? t("game.help.escape_key") : action.digit;
    return keyName === null
        ? nothing
        : html`<span class="decision-controls__key" aria-hidden="true">${keyName}</span>`;
}

/** The keys a control answers to, for assistive technology: Escape for a pass, else its digit, if any. */
function actionKeys(action: DecisionAction, escapes: boolean): string | typeof nothing {
    if (escapes) {
        return "Escape";
    }
    return action.digit === null ? nothing : String(action.digit);
}

/** A control's identity across renders, so a focused one keeps its element when a step opens or closes around it. */
function actionKey(action: DecisionAction): string {
    return JSON.stringify(action.command);
}

/** Which control takes the foreground band beside the timer: the lowest-ranked, unless it is a win. */
function bandAction(actions: readonly DecisionAction[]): DecisionAction | null {
    const last = actions.at(-1);
    return last === undefined || last.rank === "win" ? null : last;
}

/** What the decision's controls draw: its controls, its countdown and where it stands. */
export type DecisionView = Pick<
    PlayDisplay,
    "actions" | "countdown" | "decisionStanding" | "keyHints"
>;

/**
 * The decision's controls by the hand, ranked, with the timer's slot after them: a desktop lays them in one row ending
 * at the hand's right end; a phone lays them in one row ending at the timer and wraps what it cannot hold above it.
 * They stay in place while the decision is open or expired, and disappear once answered.
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
    const band = bandAction(actions);
    const upper = band === null ? actions : actions.slice(0, -1);
    return html`<div
        class="decision-controls decision-controls--${decisionStanding}"
        data-upper=${upper.length}
    >
        <div class="decision-controls__upper">${repeat(upper, actionKey, (action) => ActionButton(action, onCommand, display.keyHints))}</div>
        <div class="decision-controls__band">
            ${band === null ? nothing : ActionButton(band, onCommand, display.keyHints)}${DecisionTimer(display)}
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
    return html`<div class="play-switches" role="group" aria-label=${t("game.switches.label")}>
        ${repeat(
            switches,
            (control) => control.playSwitch,
            (control) => SwitchButton(control, onCommand),
        )}<button
            type="button"
            class="play-switches__names-toggle"
            aria-pressed=${String(namesShown)}
            aria-label=${t("game.switches.names")}
            title=${t(namesShown ? "game.switches.hide_names" : "game.switches.show_names")}
            @click=${() => onCommand({ kind: "toggle_switch_names" })}
        >
            <svg class="play-switches__arrow" viewBox="0 0 10 10" aria-hidden="true">
                <polygon points=${namesShown ? "7,1 7,9 2,5" : "3,1 3,9 8,5"}></polygon>
            </svg>
        </button>
        ${namesShown ? SwitchNames(switches) : nothing}
    </div>`;
}

/** The time left to the round advance, as words on the panel itself, since a touch screen shows no tooltip. */
function ResultTime(countdown: DecisionCountdown | null): TemplateResult | typeof nothing {
    if (countdown?.kind === "running") {
        return html`<span class="round-end-result__countdown"
            >${t("game.countdown.seconds_left", { count: countdown.secondsLeft })}</span
        >`;
    }
    if (countdown?.kind === "expired") {
        return html`<span class="round-end-result__countdown round-end-result__countdown--expired"
            >${t("game.timer.time_up")}</span
        >`;
    }
    return nothing;
}

/**
 * The round result's controls at the panel's foot, beside the scores: its primary button (Next, then OK), focused as it
 * first shows so Enter or Space presses it, with the time left to the round advance under its label, or, once the seat
 * confirmed, that it waits for the others with the time still
 * counting down. Both stack in one cell, the one not shown kept hidden in place, so confirming never resizes the panel.
 * Only the countdown's thresholds are announced.
 */
function ResultControlsView(
    result: ResultControls | null,
    onCommand: PlayBoardProps["onCommand"],
): TemplateResult | undefined {
    if (result === null) {
        return undefined;
    }
    const { action, countdown, waiting } = result;
    const confirm =
        action === null
            ? html`<button
                  type="button"
                  class="round-end-result__confirm round-end-result__ghost"
                  aria-hidden="true"
                  tabindex="-1"
                  disabled
              >
                  <span class="round-end-result__confirm-label">${t("common.ok")}</span>
                  ${ResultTime(countdown)}
              </button>`
            : html`<button
                  type="button"
                  class="round-end-result__confirm"
                  data-focus-key=${PANEL_CONTROL_FOCUS_KEY}
                  aria-label=${action.label}
                  ${focusOnFirstRender()}
                  @click=${() => onCommand(action.command)}
              >
                  <span class="round-end-result__confirm-label">${action.label}</span>
                  ${ResultTime(countdown)}
              </button>`;
    return html`<span class="round-end-result__controls">
        ${confirm}
        <span
            class=${action === null ? "round-end-result__wait" : "round-end-result__wait round-end-result__ghost"}
            aria-hidden=${action === null ? nothing : "true"}
        >
            ${waiting || action !== null ? html`<span class="round-end-result__waiting">${t("game.result.waiting")}</span>` : nothing}
            ${ResultTime(countdown)}
        </span>
        <span class="round-end-result__announce" aria-live="polite">${countdownAnnouncement(countdown)}</span>
    </span>`;
}

/**
 * The opening screen's OK at the seating's foot, focused as it first shows so Enter or Space presses it, with the
 * seconds the screen still shows under its label, as a round result's confirm counts its time. Once the seat sent its
 * start confirm the same button stays in place, disabled, saying it waits for the others, its time still counting. Its
 * label reserves the waiting label's width (`data-reserve`), so the button never grows when pressed.
 */
function OpeningControlsView(
    opening: OpeningControls | null,
    onCommand: PlayBoardProps["onCommand"],
): TemplateResult | undefined {
    if (opening === null || (opening.action === null && !opening.waiting)) {
        return undefined;
    }
    const { action, secondsLeft } = opening;
    const label = action?.label ?? t("game.result.waiting");
    return html`<div class="seating__actions">
    <button
      type="button"
      class="seating__action seating__confirm"
      data-focus-key=${PANEL_CONTROL_FOCUS_KEY}
      aria-label=${label}
      ?disabled=${action === null}
      ${focusOnFirstRender()}
      @click=${() => {
          if (action !== null) {
              onCommand(action.command);
          }
      }}
    >
      <span class="seating__confirm-label" data-reserve=${t("game.result.waiting")}><span>${label}</span></span>
      ${secondsLeft === null ? nothing : html`<span class="seating__countdown">${t("game.countdown.seconds_left", { count: secondsLeft })}</span>`}
    </button>
  </div>`;
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
            { href: links.replay, kind: "link", label: t("game.end.replay") },
            { href: links.history, kind: "link", label: t("common.game_history") },
        );
    }
    actions.push({
        kind: "button",
        label: t("common.lobby"),
        onClick: () => onCommand(display.leave.command),
        primary: true,
    });
    return actions;
}

const CLOSE_NOTICE: PlayCommand = { kind: "close_notice" };
const TOGGLE_SETTINGS: PlayCommand = { kind: "toggle_settings" };
const CLOSE_SETTINGS: PlayCommand = { kind: "close_settings" };
const TOGGLE_SOUND: PlayCommand = { kind: "toggle_sound" };
const TOGGLE_ANIMATIONS: PlayCommand = { kind: "toggle_animations" };
const SHOW_CONTROLS: PlayCommand = { kind: "show_controls" };

/** What goes on beneath a notice's sheet: play, and the decision or round confirm the player owes with its seconds. */
function sheetNoteText(countdown: NoticeSheetDisplay["countdown"]): TemplateResult | string {
    if (countdown?.kind === "running") {
        const key =
            countdown.clock?.inBank === true
                ? "game.sheet.note_owed_bank_seconds"
                : "game.sheet.note_owed_seconds";
        const text = t(key, { count: countdown.secondsLeft, move: moveName(countdown.move) });
        return withSecondsFigure(text, countdown.secondsLeft, "notice-sheet__seconds");
    }
    if (countdown?.kind === "expired") {
        return t("game.sheet.note_expired", { expired: expiredSentence(countdown.move) });
    }
    return t("game.sheet.note");
}

function SheetNote(countdown: NoticeSheetDisplay["countdown"]): TemplateResult {
    return html`<p class="notice-sheet__note">${sheetNoteText(countdown)}</p>
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
        case "controls": {
            return ControlsHelp(panel.rightClick, onCommand);
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
                seatingControls: OpeningControlsView(display.opening, onCommand),
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
 * dismisses it. A press on one of the viewer's tiles sends the intent the display gives it (`playInput` holds a
 * finger's first tap on a discard back to lift the tile), and a tile with none sends nothing; turning the result's page is a command too. While an end, the leave question or a notice's sheet blocks
 * the board, the board under it is inert. Each new showing of calls is read out once.
 */
export function PlayBoard(props: PlayBoardProps): TemplateResult {
    const { clock, display, menuExtra, onCommand, onLanguage, onTileLabels, onWinds } = props;
    const { overlay } = display;
    const inert = overlay?.blocksBoard ?? false;
    function onTile(tileId: number): void {
        const intent = display.tileIntents.get(tileId);
        if (intent !== undefined) {
            onCommand({ intent, kind: "intent" });
        }
    }
    return GameBoard({
        actions: DecisionControls(display, onCommand),
        animationsOn: display.animationsOn,
        callouts: display.callouts,
        debug: false,
        furiten: display.furiten,
        inert,
        input: playInput(display, onCommand, clock),
        localHand: { onTile, tileAction: display.tileAction },
        matchResult: display.matchResult,
        menu: GameMenu({
            alert: display.cogAlert,
            animationsOn: display.animationsOn,
            backdrop: false,
            extra: menuExtra,
            input: {
                keyHints: display.keyHints,
                onShowControls: () => onCommand(SHOW_CONTROLS),
                onToggle: () => onCommand({ kind: "toggle_right_click" }),
                onToggleKeyHints: () => onCommand({ kind: "toggle_key_hints" }),
                rightClick: display.shortcuts.rightClickEnabled,
            },
            keepAutoWin: {
                on: display.keepAutoWin,
                onToggle: () => onCommand(intentCommand({ type: "toggle_keep_auto_win" })),
            },
            leave: {
                asks: display.leave.command.kind === "ask_leave",
                kind: "leave",
                onLeave: () => onCommand(display.leave.command),
            },
            onClose: () => onCommand(CLOSE_SETTINGS),
            onLanguage,
            onTileLabels,
            onToggleAnimations: () => onCommand(TOGGLE_ANIMATIONS),
            onToggleOpen: () => onCommand(TOGGLE_SETTINGS),
            onToggleSound: () => onCommand(TOGGLE_SOUND),
            onWinds,
            open: display.settingsOpen,
            roundTrip: display.roundTrip,
            soundOn: display.soundOn,
            status: display.status,
        }),
        motion: display.motion,
        notices: display.notices.map((notice) => boardNotice(notice, onCommand)),
        overlay: overlay === null ? undefined : OverlayPanel(overlay.panel, props),
        overlayAfterCall: overlay?.panel.kind === "result" && overlay.panel.afterCall,
        state: display.board,
        switches: PlaySwitches(display.switches, display.switchNames, onCommand),
    });
}
