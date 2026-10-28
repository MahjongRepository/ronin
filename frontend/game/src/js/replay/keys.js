import $ from "jquery";

import { HOLD_REPEAT_MS } from "./hold.js";

/** The replay's keyboard commands, by name: the strip's buttons, the help and the key bindings refer to them. */
export const COMMAND = Object.freeze({
    BACK: "back",
    NEXT: "next",
    PREV_ROUND: "prevRound",
    NEXT_ROUND: "nextRound",
    FIRST: "first",
    LAST: "last",
    PLAY: "play",
    NEXT_SEAT: "nextSeat",
    HIDE_HANDS: "hideHands",
    HELP: "help",
});

export const CLOSE_KEY = "Escape";

/** How each key is shown in the help and the buttons' titles, and named by `aria-keyshortcuts`. */
export const KEY_NAMES = Object.freeze({
    ArrowLeft: { shown: "←", aria: "ArrowLeft" },
    ArrowRight: { shown: "→", aria: "ArrowRight" },
    ArrowUp: { shown: "↑", aria: "ArrowUp" },
    ArrowDown: { shown: "↓", aria: "ArrowDown" },
    PageUp: { shown: "PgUp", aria: "PageUp" },
    PageDown: { shown: "PgDn", aria: "PageDown" },
    Home: { shown: "Home", aria: "Home" },
    End: { shown: "End", aria: "End" },
    " ": { shown: "Space", aria: "Space" },
    v: { shown: "V", aria: "V" },
    h: { shown: "H", aria: "H" },
    "?": { shown: "?", aria: "?" },
    [CLOSE_KEY]: { shown: "Esc" },
});

/** Whether a held key repeats a command: never, always, or until it reaches a result or the standings. */
const REPEAT = Object.freeze({ NEVER: "never", ALWAYS: "always", UNTIL_STOP: "until_stop" });

/**
 * Each command's keys (`KeyboardEvent.key`, a letter in lower case and matched in either case, or by its `code` where
 * the layout types no Latin letter), what it does and whether a held key repeats it. A `buttonKey` is left to a
 * focused button or switch, which it presses; a `listKey` is left to the round list and the help while the focus is in
 * them, where it moves through the list or scrolls.
 */
const COMMANDS = Object.freeze({
    [COMMAND.BACK]: {
        keys: ["ArrowLeft"],
        run: ({ viewer }) => viewer.back(),
        repeat: REPEAT.UNTIL_STOP,
    },
    [COMMAND.NEXT]: {
        keys: ["ArrowRight"],
        run: ({ viewer }) => viewer.next(),
        repeat: REPEAT.UNTIL_STOP,
    },
    [COMMAND.PREV_ROUND]: {
        keys: ["ArrowUp", "PageUp"],
        run: ({ viewer }) => viewer.prevRound(),
        repeat: REPEAT.ALWAYS,
        listKey: true,
    },
    [COMMAND.NEXT_ROUND]: {
        keys: ["ArrowDown", "PageDown"],
        run: ({ viewer }) => viewer.nextRound(),
        repeat: REPEAT.ALWAYS,
        listKey: true,
    },
    [COMMAND.FIRST]: {
        keys: ["Home"],
        run: ({ viewer }) => viewer.first(),
        repeat: REPEAT.NEVER,
        listKey: true,
    },
    [COMMAND.LAST]: {
        keys: ["End"],
        run: ({ viewer }) => viewer.last(),
        repeat: REPEAT.NEVER,
        listKey: true,
    },
    [COMMAND.PLAY]: {
        keys: [" "],
        run: ({ controls }) => controls.togglePlay(),
        repeat: REPEAT.NEVER,
        buttonKey: true,
        listKey: true,
    },
    [COMMAND.NEXT_SEAT]: {
        keys: ["v"],
        code: "KeyV",
        run: ({ controls }) => controls.viewNextSeat(),
        repeat: REPEAT.NEVER,
    },
    [COMMAND.HIDE_HANDS]: {
        keys: ["h"],
        code: "KeyH",
        run: ({ controls }) => controls.toggleHiddenHands(),
        repeat: REPEAT.NEVER,
    },
    [COMMAND.HELP]: {
        keys: ["?"],
        run: ({ controls }) => controls.toggleHelp(),
        repeat: REPEAT.NEVER,
    },
});

const COMMAND_OF_KEY = new Map(
    Object.entries(COMMANDS).flatMap(([name, { keys }]) => keys.map((key) => [key, name])),
);

const COMMAND_OF_CODE = new Map(
    Object.entries(COMMANDS)
        .filter(([, { code }]) => code !== undefined)
        .map(([name, { code }]) => [code, name]),
);

const LATIN_LETTER = /^[a-z]$/;

/** The keys of `command`, as `KEY_NAMES` names them. */
export function commandKeys(command) {
    return COMMANDS[command].keys;
}

/** The `aria-keyshortcuts` value of a command's keys. */
export function ariaKeys(command) {
    return commandKeys(command)
        .map((key) => KEY_NAMES[key].aria)
        .join(" ");
}

/** The keys of `command` as the buttons' titles show them: "↑ / PgUp". */
export function shownKeys(command) {
    return commandKeys(command)
        .map((key) => KEY_NAMES[key].shown)
        .join(" / ");
}

/** Whether Ctrl, Alt or Meta is held, or Shift unless `shift` is false: a press or scroll meant for something else. */
export function isModified(event, { shift = true } = {}) {
    return event.ctrlKey || event.altKey || event.metaKey || (shift && event.shiftKey);
}

/** The command of a key press: by its key, or by its physical key where the layout types a non-Latin letter. */
function commandOf(event) {
    if (typeof event.key !== "string" || event.key === "") {
        return undefined;
    }
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    const byKey = COMMAND_OF_KEY.get(key);
    if (byKey !== undefined || key.length !== 1 || LATIN_LETTER.test(key)) {
        return byKey;
    }
    return COMMAND_OF_CODE.get(event.code);
}

/** A key typed as a character (`?`, a letter) may need Shift; Shift with any other key is a modified press. */
function isCharacter(key) {
    return key.length === 1 && key !== " ";
}

/** A field that takes typed keys itself: a text field or a select, never a checkbox, which keys only toggle. */
function isFormField(element) {
    return (
        element instanceof Element &&
        element.closest('select, textarea, [contenteditable], input:not([type="checkbox"])') !==
            null
    );
}

function isPressable(element) {
    return (
        element instanceof Element &&
        element.closest('button, a[href], input[type="checkbox"]') !== null
    );
}

/**
 * Drive the viewer from the keyboard (`COMMANDS`), Escape closing the topmost open layer. A key never reaches the
 * replay from a form field (the seat and speed choices), with Ctrl, Alt or Meta held, with Shift held on a key that is
 * not a character, or once something else handled it; Space presses a focused button or switch rather than playing. A
 * held arrow repeats its step as the held Back and Next buttons do, at their pace, and stops at a result; a fresh press
 * moves on. A held Escape closes one layer only.
 */
export function bindKeys(viewer, controls) {
    const context = { viewer, controls };
    let lastStepAt = -Infinity;
    $(window).on("keydown.replay-keys", (event) => {
        const native = event.originalEvent;
        if (native.defaultPrevented || native.isComposing || isModified(native, { shift: false })) {
            return;
        }
        if (native.key === CLOSE_KEY) {
            if (!native.repeat && controls.closeTopmost()) {
                event.preventDefault();
            }
            return;
        }
        const name = commandOf(native);
        if (name === undefined || isFormField(native.target)) {
            return;
        }
        const command = COMMANDS[name];
        if (native.shiftKey && !isCharacter(native.key)) {
            return;
        }
        if (command.buttonKey && isPressable(native.target)) {
            return;
        }
        if (command.listKey && controls.keepsNavigationKeys(native.target)) {
            return;
        }
        event.preventDefault();
        const now = performance.now();
        if (native.repeat) {
            if (command.repeat === REPEAT.NEVER || now - lastStepAt < HOLD_REPEAT_MS) {
                return;
            }
            if (command.repeat === REPEAT.UNTIL_STOP && viewer.isAtStop()) {
                return;
            }
            controls.setKeyHeld(true);
        }
        lastStepAt = now;
        command.run(context);
        if (command.repeat === REPEAT.UNTIL_STOP && viewer.isAtStop()) {
            controls.setKeyHeld(false);
        }
    });
    $(window).on("keyup.replay-keys blur.replay-keys", () => controls.setKeyHeld(false));
}

/** Stop driving the replay from the keyboard: a replay that failed is no longer shown. */
export function unbindKeys() {
    $(window).off(".replay-keys");
}
