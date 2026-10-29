/** Cancels the timer it was returned for; calling it after the timer fired does nothing. */
export type CancelTimer = () => void;

/** The time source and timer scheduler a controller is given, so a test can drive time by hand. */
export interface Clock {
    readonly now: () => number;
    /** Call `callback` once after `delayMs`, never synchronously from inside this call. */
    readonly setTimer: (delayMs: number, callback: () => void) => CancelTimer;
}

export const browserClock: Clock = {
    now: () => Date.now(),
    setTimer: (delayMs, callback) => {
        const handle = setTimeout(callback, delayMs);
        return () => clearTimeout(handle);
    },
};
