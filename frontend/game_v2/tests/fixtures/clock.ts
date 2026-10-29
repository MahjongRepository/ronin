import { type Clock } from "@/shared/clock";

export interface ManualTimer {
    readonly at: number;
    readonly callback: () => void;
    cancelled: boolean;
}

/** A clock moved by hand; `timers` keeps every callback, cancelled ones too, so a test can fire a stale one. */
export class ManualClock implements Clock {
    readonly timers: ManualTimer[] = [];
    private current = 0;

    now = (): number => this.current;

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

    advanceTo(at: number): void {
        this.current = at;
        for (const timer of this.timers.filter((t) => !t.cancelled && t.at <= at)) {
            timer.cancelled = true;
            timer.callback();
        }
    }
}
