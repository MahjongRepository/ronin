import { STEP_BUTTON_ATTRIBUTE, type StepDirection } from "@/entities/replay";
import { wheelPixels } from "@/shared/lib";
import { type ReplayKeyCommand } from "@/views/replay-page";

/** The moves a scrolling round result keeps for itself: they would scroll it. */
const SCROLL_COMMANDS: ReadonlySet<ReplayKeyCommand> = new Set([
    "first",
    "last",
    "nextRound",
    "prevRound",
]);

/** By `key`, or by `code` for the letters, so a layout that types other letters keeps them. */
const KEY_COMMANDS: ReadonlyMap<string, ReplayKeyCommand> = new Map([
    ["ArrowDown", "nextRound"],
    ["ArrowLeft", "prev"],
    ["ArrowRight", "next"],
    ["ArrowUp", "prevRound"],
    ["End", "last"],
    ["Home", "first"],
    ["KeyH", "hands"],
    ["KeyV", "view"],
    ["PageDown", "nextRound"],
    ["PageUp", "prevRound"],
    ["Space", "play"],
]);

/** Where a key belongs to something else: a field typed into, the round list's own keys. */
const OWN_KEYS_SELECTOR = "input, textarea, select, [contenteditable], .round-list";
/** The panel over the board a round's result shows in, which scrolls when the result is taller than the board. */
const OVERLAY_PANEL_SELECTOR = ".board-overlay__panel";
/** Where Space and Enter activate the focused control itself, which the page must not repeat. */
const ACTIVATED_SELECTOR = "button, a[href], summary, [role='button']";
/** Where a click leaves the round list open: the list itself and its toggle. */
const ROUND_LIST_SELECTOR = ".round-list, .replay-controls__option--rounds";

/** A primary button's bit in a pointer event's `buttons`. */
const PRIMARY_BUTTON = 1;

/** The events a held step button follows its pointer by. */
export const HOLD_EVENTS = [
    "pointerup",
    "lostpointercapture",
    "pointercancel",
    "pointerleave",
    "pointermove",
] as const;

/** What a held step button's pointer did: its press ended (or was cancelled), or it moved on or off the button. */
export type HoldInput =
    | { readonly kind: "hold_end"; readonly cancelled: boolean }
    | { readonly kind: "hold_pointer"; readonly over: boolean };

function elementOf(target: EventTarget | null): Element | null {
    return target instanceof Element ? target : null;
}

function isModified(event: KeyboardEvent): boolean {
    return (
        event.isComposing ||
        event.key === "Process" ||
        event.ctrlKey ||
        event.altKey ||
        event.metaKey
    );
}

/**
 * The step a key activating a step button takes (Enter or Space on it), or null. The page takes it as that step, so a
 * held key pauses where a result shows, as an arrow key does, rather than repeating the button's clicks past it.
 */
export function stepKeyDirection(event: KeyboardEvent): StepDirection | null {
    if (isModified(event) || (event.key !== "Enter" && event.key !== " ")) {
        return null;
    }
    const step = elementOf(event.target)
        ?.closest(`[${STEP_BUTTON_ATTRIBUTE}]`)
        ?.getAttribute(STEP_BUTTON_ATTRIBUTE);
    return step === "next" || step === "prev" ? step : null;
}

/**
 * Whether `element` is inside the panel over the board while that panel, or a part of it between the element and the
 * panel (a round result's yaku, value or score rows), scrolls.
 */
function inScrollingPanel(element: Element): boolean {
    const panel = element.closest(OVERLAY_PANEL_SELECTOR);
    if (panel === null) {
        return false;
    }
    for (let node: Element | null = element; node !== panel; node = node.parentElement) {
        if (node === null) {
            return false;
        }
        if (node.scrollHeight > node.clientHeight && scrollsVertically(node)) {
            return true;
        }
    }
    return panel.scrollHeight > panel.clientHeight;
}

function scrollsVertically(element: Element): boolean {
    const { overflowY } = getComputedStyle(element);
    return overflowY === "auto" || overflowY === "scroll";
}

/**
 * The page's command for a key, or null where the key is not the page's: typed into a field or composed by an input
 * method, held with a modifier, inside the round list, Space and Enter on a control they activate
 * (a step button's are its step), or a key that would scroll a round's result scrolling inside its panel.
 */
export function keyCommand(event: KeyboardEvent): ReplayKeyCommand | null {
    const step = stepKeyDirection(event);
    if (step !== null) {
        return step;
    }
    const target = elementOf(event.target);
    if (isModified(event) || target?.closest(OWN_KEYS_SELECTOR)) {
        return null;
    }
    const command = KEY_COMMANDS.get(event.key) ?? KEY_COMMANDS.get(event.code) ?? null;
    if (command === "play" && target?.closest(ACTIVATED_SELECTOR)) {
        return null;
    }
    return command !== null &&
        SCROLL_COMMANDS.has(command) &&
        target !== null &&
        inScrollingPanel(target)
        ? null
        : command;
}

/**
 * A wheel turned up or down over the board, outside the round list, the notices' place (the
 * position) and a round's result scrolling in its panel, and not a pinch: its distance in pixels, the
 * step it asks for, or null where the wheel is not the page's.
 */
export function boardWheel(
    event: WheelEvent,
): { readonly deltaPx: number; readonly direction: StepDirection } | null {
    const over = elementOf(event.target);
    const taken =
        event.deltaY !== 0 &&
        !event.ctrlKey &&
        over !== null &&
        over.closest(".board-page__board") !== null &&
        over.closest(".round-list, .board-notices") === null &&
        !inScrollingPanel(over);
    return taken
        ? { deltaPx: wheelPixels(event), direction: event.deltaY > 0 ? "next" : "prev" }
        : null;
}

/** The step button a primary pointer pressed with its main button, else null. */
export function pressedStepButton(event: PointerEvent): HTMLElement | null {
    const button = event.currentTarget;
    return event.button === 0 && event.isPrimary && button instanceof HTMLElement ? button : null;
}

/** Whether a pointer event stands over `element`'s box. */
function isOver(element: Element, event: MouseEvent): boolean {
    const { bottom, left, right, top } = element.getBoundingClientRect();
    return (
        event.clientX >= left &&
        event.clientX <= right &&
        event.clientY >= top &&
        event.clientY <= bottom
    );
}

/**
 * What one of `HOLD_EVENTS` on the held `button` says: a release or a lost capture ends the hold, a cancel ends it
 * cancelled, leaving or moving off the button pauses it, and a pointer back with its button released ends it, as a
 * release off the button may never reach it.
 */
export function holdInput(event: Event, button: Element): HoldInput | null {
    if (event.type === "pointerup" || event.type === "lostpointercapture") {
        return { cancelled: false, kind: "hold_end" };
    }
    if (event.type === "pointercancel") {
        return { cancelled: true, kind: "hold_end" };
    }
    if (event.type === "pointerleave") {
        return { kind: "hold_pointer", over: false };
    }
    if (!(event instanceof MouseEvent)) {
        return null;
    }
    return (event.buttons & PRIMARY_BUTTON) === 0
        ? { cancelled: false, kind: "hold_end" }
        : { kind: "hold_pointer", over: isOver(button, event) };
}

/** Whether a click landed outside `host`'s round list and its toggle, which closes the list. */
export function isOutsideRoundList(event: MouseEvent, host: HTMLElement): boolean {
    const inside = elementOf(event.target)?.closest(ROUND_LIST_SELECTOR);
    return !inside || !host.contains(inside);
}
