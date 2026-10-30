import { type CancelTimer, type Clock } from "@/shared/clock";

/** One timer a view keeps armed to its state's next deadline, which comes back as a tick. */
export interface DeadlineTimer {
    /** Arm the timer to `deadline`, unless it is armed to it already; null disarms it. */
    readonly arm: (deadline: number | null) => void;
    readonly disarm: () => void;
}

interface ArmedTimer {
    readonly cancel: CancelTimer;
    readonly deadline: number;
    readonly token: object;
}

/**
 * The view's one timer on `clock`: when its deadline comes it calls `onDue` with the deadline's logical time, never
 * before it, so a tick never comes early; a timer replaced or disarmed before it fires calls nothing.
 */
export function createDeadlineTimer(clock: Clock, onDue: (at: number) => void): DeadlineTimer {
    let armed: ArmedTimer | null = null;
    function disarm(): void {
        armed?.cancel();
        armed = null;
    }
    function arm(deadline: number | null): void {
        if (deadline === (armed?.deadline ?? null)) {
            return;
        }
        disarm();
        if (deadline === null) {
            return;
        }
        const token = {};
        const cancel = clock.setTimer(Math.max(0, deadline - clock.now()), () => {
            if (armed?.token !== token) {
                return;
            }
            armed = null;
            onDue(Math.max(clock.now(), deadline));
        });
        armed = { cancel, deadline, token };
    }
    return { arm, disarm };
}
