import { type CancelTimer, type Clock } from "@/shared/clock";

/** Writes the latest value given, at most once per interval. */
export interface ThrottledWriter<Value> {
    /** Write `value` now, or once the interval since the last write has passed, the latest value then winning. */
    readonly write: (value: Value) => void;
    /** Write a value still waiting now. */
    readonly flush: () => void;
    /** Drop a value still waiting, and write nothing more. */
    readonly cancel: () => void;
}

/**
 * A writer that keeps a sink from being written more often than once per `intervalMs` of the clock's time: a value
 * given within the interval waits for its end, and a later one replaces it.
 */
export function createThrottledWriter<Value>(
    clock: Clock,
    intervalMs: number,
    sink: (value: Value) => void,
): ThrottledWriter<Value> {
    let lastWrite = Number.NEGATIVE_INFINITY;
    let pending: { readonly value: Value } | null = null;
    let cancelTimer: CancelTimer | null = null;
    let cancelled = false;

    function flush(): void {
        cancelTimer?.();
        cancelTimer = null;
        if (pending === null || cancelled) {
            return;
        }
        const { value } = pending;
        pending = null;
        lastWrite = clock.now();
        sink(value);
    }

    function write(value: Value): void {
        if (cancelled) {
            return;
        }
        pending = { value };
        if (cancelTimer !== null) {
            return;
        }
        const waitMs = lastWrite + intervalMs - clock.now();
        if (waitMs <= 0) {
            flush();
            return;
        }
        cancelTimer = clock.setTimer(waitMs, flush);
    }

    function cancel(): void {
        cancelled = true;
        pending = null;
        cancelTimer?.();
        cancelTimer = null;
    }

    return { cancel, flush, write };
}
