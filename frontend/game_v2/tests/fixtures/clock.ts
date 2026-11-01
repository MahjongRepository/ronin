import { type Clock, createSteadyClock } from "@/shared/clock";

export interface ManualTimer {
    readonly at: number;
    readonly callback: () => void;
    cancelled: boolean;
}

/**
 * The wall and elapsed time sources and timers of a clock moved by hand; `timers` keeps every callback, cancelled ones
 * too, so a test can fire a stale one. `now` is the wall, which `stepWall` moves back or forward, so it is no `Clock`
 * (whose time never runs back) once stepped back; a view is given `steadyClockOn` it, as the page is `browserClock`.
 * A timer runs on elapsed time, as a browser's does.
 */
export class ManualClock {
    readonly timers: ManualTimer[] = [];
    private current = 0;
    private wallStep = 0;

    now = (): number => this.current + this.wallStep;

    elapsedNow = (): number => this.current;

    setTimer = (delayMs: number, callback: () => void): (() => void) => {
        const timer: ManualTimer = { at: this.current + delayMs, callback, cancelled: false };
        this.timers.push(timer);
        return () => {
            timer.cancelled = true;
        };
    };

    /** The timer armed last, which a test fires by hand after it was replaced or cancelled. */
    lastTimer(): ManualTimer {
        const timer = this.timers.at(-1);
        if (timer === undefined) {
            throw new Error("no timer was armed");
        }
        return timer;
    }

    /**
     * Step the wall clock by `deltaMs`, as the OS setting its time does, leaving every timer where it was; a forward
     * step is also how a sleep that pauses elapsed time looks.
     */
    stepWall(deltaMs: number): void {
        this.wallStep += deltaMs;
    }

    advanceTo(at: number): void {
        this.current = at;
        for (const timer of this.timers.filter((t) => !t.cancelled && t.at <= at)) {
            timer.cancelled = true;
            timer.callback();
        }
    }
}

/** The steady clock a view runs on in the page, read from `clock`'s wall and elapsed time. */
export function steadyClockOn(clock: ManualClock): Clock {
    return createSteadyClock({
        elapsedNow: clock.elapsedNow,
        setTimer: clock.setTimer,
        wallNow: clock.now,
    });
}
