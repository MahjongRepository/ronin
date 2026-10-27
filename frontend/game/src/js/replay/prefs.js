import { AUTOPLAY_SPEEDS, DEFAULT_AUTOPLAY_SPEED } from "./speeds.js";

/**
 * The replay viewer's own settings, under a key of their own: `GameCtl` owns the live game's key outright and
 * rewrites it whole on every sound toggle, so nothing replay-specific is ever stored there.
 */
export const REPLAY_PREFS_KEY = "ronin.replay.prefs";

const DEFAULTS = Object.freeze({ hideHands: false, speed: DEFAULT_AUTOPLAY_SPEED });

/** Each setting's check: a stored value that fails it reads as the default. */
const VALID = Object.freeze({
    hideHands: (value) => typeof value === "boolean",
    speed: (value) => typeof value === "string" && Object.hasOwn(AUTOPLAY_SPEEDS, value),
});

function parsePrefs(text) {
    const stored = JSON.parse(text);
    const valid = Object.entries(VALID).filter(([name, isValid]) => isValid(stored?.[name]));
    return { ...DEFAULTS, ...Object.fromEntries(valid.map(([name]) => [name, stored[name]])) };
}

/** The stored settings, each missing or unreadable one at its default. */
export function readReplayPrefs() {
    try {
        const text = localStorage.getItem(REPLAY_PREFS_KEY);
        return text === null ? { ...DEFAULTS } : parsePrefs(text);
    } catch (error) {
        console.warn("[ronin] replay settings unreadable, using the defaults:", error);
        return { ...DEFAULTS };
    }
}

/** Store `changes` over the stored settings; a storage that refuses them leaves them unsaved, with a warning. */
export function writeReplayPrefs(changes) {
    try {
        localStorage.setItem(
            REPLAY_PREFS_KEY,
            JSON.stringify({ ...readReplayPrefs(), ...changes }),
        );
    } catch (error) {
        console.warn("[ronin] replay settings not saved:", error);
    }
}
