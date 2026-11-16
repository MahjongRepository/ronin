import { type CancelTimer, type Clock } from "@/shared/clock";

/** The page's scroll, as the rest reads and moves it. */
export type RestedPage = Pick<Window, "scrollY" | "addEventListener"> & {
    readonly scrollTo: (left: number, top: number) => void;
};

const PAGE_EVENTS = ["scroll", "touchstart", "touchend", "touchcancel"] as const;

export interface PageRest {
    readonly clock: Clock;
    /** How long the page goes without a scroll or a touch before it returns to its rest. */
    readonly quietMs: number;
    /** How far down the page rests (px), or 0 where it keeps no scroll room. */
    readonly restAt: () => number;
}

export interface RestingPage {
    /** Return the page to its rest now, unless a finger is on it. */
    readonly rest: () => void;
    readonly stop: () => void;
}

/**
 * Keep `page` at its rest, with scroll room on both sides of it: it returns there `quietMs` after its last scroll, a
 * fling's and a bounce's included, and never while a finger is down, whose drag a jump would cut short. The supported
 * Safari has no `scrollend`.
 */
export function keepPageRested(
    page: RestedPage,
    { clock, quietMs, restAt }: PageRest,
): RestingPage {
    const listeners = new AbortController();
    let cancelTimer: CancelTimer | null = null;
    let touching = false;

    function rest(): void {
        const at = restAt();
        if (touching || at <= 0 || Math.abs(page.scrollY - at) < 1) {
            return;
        }
        page.scrollTo(0, at);
    }

    function restOnceQuiet(): void {
        cancelTimer?.();
        cancelTimer = clock.setTimer(quietMs, rest);
    }

    function onPageEvent(event: Event | TouchEvent): void {
        if ("touches" in event) {
            touching = event.touches.length > 0;
        }
        restOnceQuiet();
    }

    for (const type of PAGE_EVENTS) {
        page.addEventListener(type, onPageEvent, { passive: true, signal: listeners.signal });
    }
    return {
        rest,
        stop: () => {
            listeners.abort();
            cancelTimer?.();
        },
    };
}
