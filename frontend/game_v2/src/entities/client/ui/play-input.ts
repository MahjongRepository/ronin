import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import { type ElementPart, type PartInfo, PartType, directive } from "lit-html/directive.js";

import { type PlayDisplay } from "@/entities/client/model/play-display";
import { type PlayShortcut, leavesBoardKeys } from "@/entities/client/model/play-shortcuts";
import { type PlayCommand } from "@/entities/client/model/play-ui";
import { DECISION_ACTION_FOCUS_KEY } from "@/entities/table";
import { HAND_TILE_FOCUS_KEY, PLAYABLE_TILE_FOCUS_KEY } from "@/entities/tile";
import { type Clock } from "@/shared/clock";
import { focusByKey, keyedControls } from "@/shared/lib";

type CommandHandler = (command: PlayCommand) => void;

/**
 * How long after an Escape or a right-click with a shortcut the next of its kind is dropped, so a double press cannot
 * close a panel and then discard, or answer a decision and then the one its answer opened. Windows' default
 * double-click time.
 */
export const SHORTCUT_SETTLE_MS = 500;

/**
 * How long after a digit key acted the same digit is dropped once the controls it presses changed (a call's choice of
 * tiles opening under it, the next decision), so a double tap cannot open a choice and take its first option unseen.
 * Another digit acts at once.
 */
export const DIGIT_SETTLE_MS = 500;

interface PointerPress {
    readonly revision: number;
    readonly pointerId: number;
    readonly target: EventTarget | null;
    readonly button: number;
}

interface KeyPress {
    readonly key: string;
    readonly revision: number;
}

interface DigitPress {
    readonly digit: number;
    readonly at: number;
    readonly scope: string;
}

/** A digit key as the decision controls take it: the number row by position, the numpad only while it types digits. */
function actionDigit(event: KeyboardEvent): number | null {
    const row = /^Digit(?<digit>[1-9])$/u.exec(event.code)?.groups?.digit;
    if (row !== undefined) {
        return Number(row);
    }
    const pad = /^Numpad(?<digit>[1-9])$/u.exec(event.code)?.groups?.digit;
    return pad !== undefined && event.key === pad ? Number(pad) : null;
}

function isModified(event: MouseEvent | KeyboardEvent): boolean {
    return event.altKey || event.ctrlKey || event.metaKey || event.shiftKey;
}

function isField(target: EventTarget | null): boolean {
    return (
        target instanceof Element &&
        target.closest(
            'input, textarea, select, [contenteditable]:not([contenteditable="false"])',
        ) !== null
    );
}

function consume(event: Event): void {
    event.preventDefault();
    event.stopImmediatePropagation();
}

function isPlayControl(target: EventTarget | null): boolean {
    return (
        target instanceof Element &&
        target.closest(
            `[data-focus-key~="${HAND_TILE_FOCUS_KEY}"], [data-focus-key~="${DECISION_ACTION_FOCUS_KEY}"]`,
        ) !== null
    );
}

function playableTileId(target: EventTarget | null): number | null {
    const tile =
        target instanceof Element
            ? target.closest<HTMLElement>(`[data-focus-key~="${PLAYABLE_TILE_FOCUS_KEY}"]`)
            : null;
    return tile === null ? null : Number(tile.dataset.tileId);
}

/** The way a key steps through the hand: an arrow, or A and D by position (ф and в on a Russian layout). */
function tileStep(event: KeyboardEvent): "ArrowLeft" | "ArrowRight" | null {
    if (event.key === "ArrowLeft" || event.code === "KeyA") {
        return "ArrowLeft";
    }
    return event.key === "ArrowRight" || event.code === "KeyD" ? "ArrowRight" : null;
}

/**
 * Move the focus to the next tile an arrow names, wrapping round the hand's edges: among the playable tiles, or every
 * tile of the hand while none plays (another's turn), so the focus waits on a tile for the turn to come.
 */
function moveTileFocus(board: HTMLElement, target: EventTarget | null, key: string): boolean {
    const tiles = keyedControls(board, HAND_TILE_FOCUS_KEY);
    if (!(target instanceof HTMLElement) || !board.contains(target)) {
        return false;
    }
    const playable = keyedControls(board, PLAYABLE_TILE_FOCUS_KEY);
    const stops = playable.length > 0 ? playable : tiles;
    const index = tiles.indexOf(target);
    const next =
        key === "ArrowRight"
            ? (stops.find((tile) => tiles.indexOf(tile) > index) ?? stops.at(0))
            : (stops.findLast((tile) => index === -1 || tiles.indexOf(tile) < index) ??
              stops.at(-1));
    next?.focus();
    return stops.length > 0;
}

class PlayInput extends AsyncDirective {
    private board: HTMLElement | null = null;
    private display: PlayDisplay | null = null;
    private onCommand: CommandHandler | null = null;
    private clock: Clock | null = null;
    private listeners: AbortController | null = null;
    private revision = 0;
    private pointer: PointerPress | null = null;
    private activation: KeyPress | null = null;
    private blockClick = false;
    private fingerTap = false;
    private lastRightClickAt = Number.NEGATIVE_INFINITY;
    private lastEscapeAt = Number.NEGATIVE_INFINITY;
    private lastDigit: DigitPress | null = null;

    constructor(partInfo: PartInfo) {
        super(partInfo);
        if (partInfo.type !== PartType.ELEMENT) {
            throw new Error("playInput belongs on an element");
        }
    }

    render(_display: PlayDisplay, _onCommand: CommandHandler, _clock: Clock): typeof nothing {
        return nothing;
    }

    override update(
        part: ElementPart,
        [display, onCommand, clock]: [PlayDisplay, CommandHandler, Clock],
    ): typeof nothing {
        if (display.shortcuts.scope !== this.display?.shortcuts.scope) {
            this.revision += 1;
        }
        this.display = display;
        this.onCommand = onCommand;
        this.clock = clock;
        if (part.element instanceof HTMLElement && this.board !== part.element) {
            this.board = part.element;
            this.listen();
        }
        return nothing;
    }

    private listen(): void {
        this.listeners?.abort();
        this.listeners = new AbortController();
        const options = { capture: true, signal: this.listeners.signal };
        this.board?.addEventListener("keydown", this.onKeydown, options);
        this.board?.addEventListener("keyup", this.onKeyup, options);
        this.listenPointer(options);
        this.board?.addEventListener("focusout", this.onFocusout, options);
        this.board?.ownerDocument.defaultView?.addEventListener("blur", this.cancelPresses, {
            signal: this.listeners.signal,
        });
        if (this.board !== null) {
            this.board.tabIndex = -1;
        }
    }

    private listenPointer(options: AddEventListenerOptions): void {
        this.board?.addEventListener("pointerdown", this.onPointerdown, options);
        this.board?.addEventListener("pointerup", this.onPointerup, options);
        this.board?.addEventListener("pointercancel", this.cancelPointer, options);
        this.board?.addEventListener("pointerleave", this.cancelPointer, options);
        this.board?.addEventListener("contextmenu", this.onContextmenu, options);
        this.board?.addEventListener("click", this.onClick, options);
    }

    protected override disconnected(): void {
        this.listeners?.abort();
        this.cancelPresses();
    }

    protected override reconnected(): void {
        this.listen();
    }

    private readonly cancelPointer = (event: PointerEvent): void => {
        if (event.type === "pointerleave" && event.target !== this.board) {
            return;
        }
        this.blockClick ||= this.pointer !== null;
        this.pointer = null;
    };

    private readonly onFocusout = (event: FocusEvent): void => {
        if (event.relatedTarget instanceof Node && !this.board?.contains(event.relatedTarget)) {
            this.cancelPresses();
        }
    };

    private readonly cancelPresses = (): void => {
        this.blockClick ||= this.pointer !== null || this.activation !== null;
        this.pointer = null;
        this.activation = null;
    };

    private run(shortcut: PlayShortcut): void {
        const { board } = this;
        if (board === null) {
            return;
        }
        const restore =
            shortcut.command.kind === "close_settings" ||
            isPlayControl(board.ownerDocument.activeElement);
        this.onCommand?.(shortcut.command);
        if (restore && shortcut.focusKey !== null) {
            focusByKey(board, shortcut.focusKey);
        }
    }

    /** Whether a key is none of the board's: before it is set up, already handled, composing, modified or typing. */
    private ignoresKey(event: KeyboardEvent): boolean {
        return (
            this.board === null ||
            this.display === null ||
            event.defaultPrevented ||
            event.isComposing ||
            isModified(event) ||
            isField(event.target)
        );
    }

    private readonly onKeydown = (event: KeyboardEvent): void => {
        if (!this.ignoresKey(event)) {
            this.routeKey(event);
        }
    };

    /** A key of the board's to what it does: Escape, Enter or Space, a digit, else the arrows' navigation. */
    private routeKey(event: KeyboardEvent): void {
        if (event.key === "Escape") {
            this.escape(event);
            return;
        }
        if (event.key === "Enter" || event.key === " ") {
            this.activate(event);
            return;
        }
        if (!this.pressedDigit(event)) {
            this.navigate(event);
        }
    }

    /** Whether the key was a digit, pressing its decision control if one has it. */
    private pressedDigit(event: KeyboardEvent): boolean {
        const digit = actionDigit(event);
        if (digit === null) {
            return false;
        }
        this.pressDigit(event, digit);
        return true;
    }

    /** A digit key presses its decision control once per press, never the control a quick second tap would remap to. */
    private pressDigit(event: KeyboardEvent, digit: number): void {
        const { clock, display } = this;
        const shortcut = display?.shortcuts.digits.get(digit);
        if (shortcut === undefined || display === null || clock === null) {
            return;
        }
        consume(event);
        const press: DigitPress = { at: clock.now(), digit, scope: display.shortcuts.scope };
        if (event.repeat || this.remapsDigit(press)) {
            return;
        }
        this.lastDigit = press;
        this.run(shortcut);
    }

    /** Whether the same digit acted moments ago on controls that have since changed under it. */
    private remapsDigit(press: DigitPress): boolean {
        const last = this.lastDigit;
        return (
            last?.digit === press.digit &&
            last.scope !== press.scope &&
            press.at - last.at < DIGIT_SETTLE_MS
        );
    }

    private navigate(event: KeyboardEvent): void {
        const { board, display } = this;
        if (
            board === null ||
            display === null ||
            !leavesBoardKeys(display.overlay) ||
            display.settingsOpen
        ) {
            return;
        }
        const step = tileStep(event);
        if (step !== null && moveTileFocus(board, event.target, step)) {
            consume(event);
        }
    }

    /** Escape runs its shortcut once per press, never again within `SHORTCUT_SETTLE_MS` of the last one that had one. */
    private escape(event: KeyboardEvent): void {
        const shortcut = this.display?.shortcuts.escape;
        consume(event);
        if (event.repeat || shortcut === null || shortcut === undefined || this.clock === null) {
            return;
        }
        const now = this.clock.now();
        const settled = now - this.lastEscapeAt >= SHORTCUT_SETTLE_MS;
        this.lastEscapeAt = now;
        if (settled) {
            this.run(shortcut);
        }
    }

    /** Enter or Space: a focused control's own press, else the display's confirm shortcut, once per press. */
    private activate(event: KeyboardEvent): void {
        const shortcut = this.display?.shortcuts.confirm;
        const onControl =
            event.target instanceof Element && event.target.closest("button, a, summary") !== null;
        if (onControl || shortcut === null || shortcut === undefined) {
            this.armKey(event);
            return;
        }
        consume(event);
        if (!event.repeat) {
            this.run(shortcut);
        }
    }

    private armKey(event: KeyboardEvent): void {
        if (
            !(event.target instanceof Element) ||
            event.target.closest("button, a, summary") === null
        ) {
            return;
        }
        if (event.repeat) {
            consume(event);
            return;
        }
        this.activation = { key: event.key, revision: this.revision };
        this.blockClick = false;
        this.fingerTap = false;
    }

    private readonly onKeyup = (event: KeyboardEvent): void => {
        const press = this.activation;
        if (press === null || press.key !== event.key) {
            return;
        }
        this.activation = null;
        this.blockClick = event.key === " " && press.revision !== this.revision;
        if (this.blockClick) {
            consume(event);
        }
    };

    private acceptsRightClick(event: MouseEvent): boolean {
        return this.display?.shortcuts.rightClickEnabled === true && this.ownsRightClick(event);
    }

    /**
     * Whether a right-click there is the board's, shortcuts on or off: anywhere a shortcut would act, or a panel would
     * close, never a field, a link, a modified click or the board's other buttons, which keep the browser's menu.
     */
    private ownsRightClick(event: MouseEvent): boolean {
        const { display } = this;
        const { target } = event;
        if (
            display === null ||
            isModified(event) ||
            isField(target) ||
            !(target instanceof Element) ||
            target.closest("a") !== null
        ) {
            return false;
        }
        const command = display.shortcuts.rightClick?.command.kind;
        const closing =
            command === "close_settings" ||
            command === "cancel_leave" ||
            command === "close_notice" ||
            command === "close_controls";
        return (
            closing ||
            target.closest("button, nav, .play-switches, summary") === null ||
            isPlayControl(target)
        );
    }

    private readonly onPointerdown = (event: PointerEvent): void => {
        this.blockClick = false;
        this.fingerTap = false;
        this.pointer = null;
        if (
            !event.isPrimary ||
            event.defaultPrevented ||
            isModified(event) ||
            isField(event.target)
        ) {
            return;
        }
        if (
            event.button !== 0 &&
            (event.button !== 2 || event.pointerType !== "mouse" || !this.acceptsRightClick(event))
        ) {
            return;
        }
        this.pointer = {
            button: event.button,
            pointerId: event.pointerId,
            revision: this.revision,
            target: event.target,
        };
        if (event.button === 0 && this.takesFocusOnPress(event.target)) {
            this.board?.focus();
        }
    };

    /**
     * Whether a primary press gives the board the focus, so its keys work after a mouse plays: off its controls, and on
     * one too while the focus is outside the board (Safari focuses no button a click presses).
     */
    private takesFocusOnPress(target: EventTarget | null): boolean {
        const { board } = this;
        if (board === null || !(target instanceof Element)) {
            return false;
        }
        const onControl = target.closest("button, a, summary, input, textarea, select") !== null;
        return !onControl || !board.contains(board.ownerDocument.activeElement);
    }

    private readonly onPointerup = (event: PointerEvent): void => {
        const press = this.pointer;
        this.pointer = null;
        if (
            press === null ||
            press.pointerId !== event.pointerId ||
            press.button !== event.button
        ) {
            return;
        }
        this.blockClick = press.revision !== this.revision;
        this.fingerTap = event.pointerType === "touch";
        if (
            event.button !== 2 ||
            this.blockClick ||
            event.defaultPrevented ||
            !this.acceptsRightClick(event) ||
            press.target !== event.target
        ) {
            return;
        }
        this.rightClick(event);
    };

    private rightClick(event: PointerEvent): void {
        const shortcut = this.display?.shortcuts.rightClick;
        if (shortcut === null || shortcut === undefined || this.clock === null) {
            return;
        }
        consume(event);
        const now = this.clock.now();
        const settled = now - this.lastRightClickAt >= SHORTCUT_SETTLE_MS;
        this.lastRightClickAt = now;
        if (settled) {
            this.run(shortcut);
        }
    }

    private readonly onContextmenu = (event: MouseEvent): void => {
        if (event.button === 2 && this.ownsRightClick(event)) {
            event.preventDefault();
        }
    };

    private readonly onClick = (event: MouseEvent): void => {
        const { fingerTap } = this;
        this.fingerTap = false;
        if (
            this.blockClick ||
            (this.activation !== null && this.activation.revision !== this.revision)
        ) {
            consume(event);
            this.blockClick = false;
            return;
        }
        if (this.endedByClosingSettings(event)) {
            return;
        }
        if (fingerTap) {
            this.armByFinger(event);
        }
    };

    /**
     * A pointer's click outside the open settings menu closes it: on a playable tile the click goes on to the tile, and
     * anywhere else it ends here, as the whole of the gesture. A keyboard's or assistive technology's activation (no
     * click count) has aimed at its control, so it leaves the menu alone.
     */
    private endedByClosingSettings(event: MouseEvent): boolean {
        const { target } = event;
        if (
            !this.display?.settingsOpen ||
            event.detail === 0 ||
            (target instanceof Element && target.closest(".game-menu") !== null)
        ) {
            return false;
        }
        this.onCommand?.({ kind: "close_settings" });
        if (playableTileId(target) !== null) {
            return false;
        }
        consume(event);
        return true;
    }

    /**
     * A finger has no hover, so its first tap on a discardable tile only lifts it; the tap that follows on that tile
     * is left to discard it, a tap on another moves the lift there, and one anywhere else drops it.
     */
    private armByFinger(event: MouseEvent): void {
        const armed = this.display?.armedTile ?? null;
        const tileId = playableTileId(event.target);
        if (tileId === null) {
            if (armed !== null) {
                this.onCommand?.({ kind: "arm_tile", tileId: null });
            }
            return;
        }
        if (tileId !== armed && this.display?.tileIntents.get(tileId)?.type === "discard") {
            consume(event);
            this.onCommand?.({ kind: "arm_tile", tileId });
        }
    }
}

export const playInput = directive(PlayInput);
