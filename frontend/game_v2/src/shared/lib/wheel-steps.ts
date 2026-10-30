/**
 * A wheel gesture turned into steps: the distance it has run in one direction, the steps taken, and whether a step
 * landed where it must pause, after which the gesture takes no more until it rests.
 */
export interface WheelGesture {
    readonly total: number;
    readonly steps: number;
    readonly lastEventAt: number;
    readonly lastStepAt: number;
    readonly halted: boolean;
}

/** The distance before the first step: one mouse notch at once, a trackpad's first ticks not yet. */
const FIRST_STEP_PX = 30;
/** The distance for each step after the first. */
const NEXT_STEP_PX = 100;
/** The least time between two steps of one gesture. */
const STEP_INTERVAL_MS = 150;
/** A pause in the wheel this long ends its gesture. */
const REST_MS = 200;

const PX_PER_DELTA_MODE = [1, 40, 800] as const;

/** A wheel event's vertical distance in pixels, whichever unit (pixels, lines, pages) the browser gave it in. */
export function wheelPixels(event: WheelEvent): number {
    return event.deltaY * (PX_PER_DELTA_MODE[event.deltaMode] ?? 1);
}

function freshGesture(): WheelGesture {
    return {
        halted: false,
        lastEventAt: Number.NEGATIVE_INFINITY,
        lastStepAt: Number.NEGATIVE_INFINITY,
        steps: 0,
        total: 0,
    };
}

/**
 * The gesture after a wheel event of `deltaPx` at `now`, and the step it takes: 1 forward, -1 back or 0. A rest or a
 * change of direction starts a new gesture, a halted one included.
 */
export function wheelStep(
    gesture: WheelGesture | null,
    deltaPx: number,
    now: number,
): { readonly gesture: WheelGesture; readonly step: -1 | 0 | 1 } {
    const direction = deltaPx > 0 ? 1 : -1;
    const continues =
        gesture !== null &&
        now - gesture.lastEventAt <= REST_MS &&
        Math.sign(gesture.total) !== -direction;
    const base = continues ? gesture : freshGesture();
    const total = base.total + deltaPx;
    const due =
        !base.halted &&
        Math.abs(total) >= FIRST_STEP_PX + base.steps * NEXT_STEP_PX &&
        now - base.lastStepAt >= STEP_INTERVAL_MS;
    return {
        gesture: {
            halted: base.halted,
            lastEventAt: now,
            lastStepAt: due ? now : base.lastStepAt,
            steps: due ? base.steps + 1 : base.steps,
            total,
        },
        step: due ? direction : 0,
    };
}
