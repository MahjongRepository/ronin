import { type CancelTimer, type Clock } from "@/shared/clock";

export interface ScrollSettling {
    readonly clock: Clock;
    readonly quietMs: number;
    readonly listener: () => void;
}

/**
 * Call `listener` each time `target` has gone `quietMs` without a scroll event, and return how to stop. The supported
 * Safari has no `scrollend`, and a phone keeps sending `scroll` through a fling and its bounce.
 */
export function onScrollSettled(
    target: EventTarget,
    { clock, quietMs, listener }: ScrollSettling,
): () => void {
    let cancelTimer: CancelTimer | null = null;

    function onScroll(): void {
        cancelTimer?.();
        cancelTimer = clock.setTimer(quietMs, listener);
    }

    target.addEventListener("scroll", onScroll, { passive: true });
    return () => {
        target.removeEventListener("scroll", onScroll);
        cancelTimer?.();
    };
}
