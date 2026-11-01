/** Cancels the timer it was returned for; calling it after the timer fired does nothing. */
export type CancelTimer = () => void;

/** The time source and timer scheduler a controller is given, so a test can drive time by hand. */
export interface Clock {
    /** Wall time in ms that never runs back, so a deadline set from one reading is never put off by a later one. */
    readonly now: () => number;
    /** Call `callback` once after `delayMs`, never synchronously from inside this call. */
    readonly setTimer: (delayMs: number, callback: () => void) => CancelTimer;
}

/** What a steady clock reads: the wall clock, which the OS may step, and elapsed time, which only runs forward. */
export interface ClockSources {
    readonly wallNow: () => number;
    /** Elapsed time from any origin; it may pause while the device sleeps. */
    readonly elapsedNow: () => number;
    readonly setTimer: Clock["setTimer"];
}

/** How far the wall may drift from elapsed time between two readings before the gap counts as a step or a sleep. */
const WALL_STEP_TOLERANCE_MS = 1000;

/**
 * How long, in elapsed time, a back step can still be undone by a forward one: a wall set wrong and then right again
 * (by hand, or by NTP stepping twice) is set right within minutes, while a fast clock NTP sets back stays back, and a
 * forward gap long after it is far likelier a sleep.
 */
const UNDO_WINDOW_MS = 5 * 60_000;

/**
 * Wall time corrected for the OS stepping the wall clock, by comparing the wall's move between two readings with the
 * elapsed time between them. A wall that falls behind elapsed time stepped back: the gap is absorbed, so time runs on
 * at the elapsed rate. A wall that gets ahead first undoes what back steps absorbed within `UNDO_WINDOW_MS` (the
 * clock being set right again); the rest counts as time that passed, because elapsed time pauses while the device
 * sleeps on several platforms, so a sleep and a forward step look alike, and after a sleep the server's deadlines
 * really passed. What that costs: a forward step not undoing a recent back step expires everything pending (a
 * connect timeout, a healthy socket taken as silent: a reconnect, and a countdown shown short), and a sleep soon
 * after a back step counts short by up to that step. Never seeing a sleep would be worse: a dead socket and stale
 * countdowns. Within the tolerance the clock follows the wall but never runs back, so back steps under it are not
 * absorbed: each holds the clock still for its length, and several add up.
 */
export function createSteadyClock(sources: ClockSources): Clock {
    let lastWall = sources.wallNow();
    let lastElapsed = sources.elapsedNow();
    let absorbed = 0;
    let undoable = 0;
    let undoableUntil = Number.NEGATIVE_INFINITY;
    let latest = lastWall;
    function takeGap(gap: number, elapsed: number): void {
        if (elapsed > undoableUntil) {
            undoable = 0;
        }
        if (gap < -WALL_STEP_TOLERANCE_MS) {
            absorbed -= gap;
            undoable -= gap;
            undoableUntil = elapsed + UNDO_WINDOW_MS;
        } else if (gap > WALL_STEP_TOLERANCE_MS) {
            const undone = Math.min(undoable, gap);
            absorbed -= undone;
            undoable -= undone;
        }
    }
    function now(): number {
        const wall = sources.wallNow();
        const elapsed = sources.elapsedNow();
        takeGap(Math.round(wall - lastWall - (elapsed - lastElapsed)), elapsed);
        lastWall = wall;
        lastElapsed = elapsed;
        latest = Math.max(latest, wall + absorbed);
        return latest;
    }
    return { now, setTimer: sources.setTimer };
}

/** The page's one clock: the browser's wall clock made steady by `performance.now`, its timers `setTimeout`'s. */
export const browserClock: Clock = createSteadyClock({
    elapsedNow: () => performance.now(),
    setTimer: (delayMs, callback) => {
        const handle = setTimeout(callback, delayMs);
        return () => clearTimeout(handle);
    },
    wallNow: () => Date.now(),
});
