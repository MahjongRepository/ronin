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
 * How long after a right-click with a shortcut to run the next one is dropped, so a double-click cannot answer a
 * decision and then the one its answer opened. Windows' default double-click time.
 */
export const RIGHT_CLICK_SETTLE_MS = 500;

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

function moveTileFocus(board: HTMLElement, target: EventTarget | null, key: string): boolean {
    const tiles = keyedControls(board, HAND_TILE_FOCUS_KEY);
    if (!(target instanceof HTMLElement) || (target !== board && !tiles.includes(target))) {
        return false;
    }
    const playable = keyedControls(board, PLAYABLE_TILE_FOCUS_KEY);
    const index = tiles.indexOf(target);
    const next =
        key === "ArrowRight"
            ? playable.find((tile) => tiles.indexOf(tile) > index)
            : playable.findLast((tile) => index === -1 || tiles.indexOf(tile) < index);
    next?.focus();
    return playable.length > 0;
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

    private readonly onKeydown = (event: KeyboardEvent): void => {
        const { board, display } = this;
        if (
            board === null ||
            display === null ||
            event.defaultPrevented ||
            event.isComposing ||
            isModified(event) ||
            isField(event.target)
        ) {
            return;
        }
        if (event.key === "Escape") {
            this.escape(event);
            return;
        }
        if (event.key === "Enter" || event.key === " ") {
            this.activate(event);
            return;
        }
        this.navigate(event);
    };

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
        if (
            (event.key === "ArrowLeft" || event.key === "ArrowRight") &&
            moveTileFocus(board, event.target, event.key)
        ) {
            consume(event);
        }
    }

    private escape(event: KeyboardEvent): void {
        const shortcut = this.display?.shortcuts.escape;
        consume(event);
        if (!event.repeat && shortcut !== null && shortcut !== undefined) {
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
        const { display } = this;
        const { target } = event;
        if (
            !display?.shortcuts.rightClickEnabled ||
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
            command === "pin_nameplate";
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
        if (
            event.button === 0 &&
            event.target instanceof Element &&
            event.target.closest("button, a, summary, input, textarea, select") === null
        ) {
            this.board?.focus();
        }
    };

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
        const settled = now - this.lastRightClickAt >= RIGHT_CLICK_SETTLE_MS;
        this.lastRightClickAt = now;
        if (settled) {
            this.run(shortcut);
        }
    }

    private readonly onContextmenu = (event: MouseEvent): void => {
        if (event.button === 2 && this.acceptsRightClick(event)) {
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
        if (fingerTap) {
            this.armByFinger(event);
        }
    };

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
