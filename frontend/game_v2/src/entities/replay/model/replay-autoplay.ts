import { type StepEvent } from "./action-steps";
import { type NavigationIndex } from "./navigation-index";
import { type ReplayCursor, nextCursor } from "./replay-cursor";

/** Whether autoplay runs: a view's state. */
export interface AutoplayState {
    readonly playing: boolean;
}

/** How long a stop shows before autoplay moves on. */
const STOP_MS = 800;

/** How long observe autoplay holds each page of a round's result before it moves on by itself. */
export const OBSERVE_RESULT_HOLD_MS = 4000;

/** A stop's share of `STOP_MS` by its move: a deal is read longer, a draw only leads to its discard. */
const STOP_SHARE: Partial<Readonly<Record<StepEvent["type"], number>>> = {
    draw: 0.5,
    round_started: 2,
};

function isResultStop(nav: NavigationIndex, cursor: ReplayCursor): boolean {
    const { round } = nav.stops[cursor.stop];
    return nav.rounds[round].resultStop === cursor.stop;
}

/**
 * Whether autoplay or a held button or key pauses at the cursor: on any page of a
 * round's result, and at the replay's last stop, so a result is read before the next deal.
 */
export function isPauseStop(nav: NavigationIndex, cursor: ReplayCursor): boolean {
    return isResultStop(nav, cursor) || cursor.stop === nav.stops.length - 1;
}

/** How long autoplay shows the cursor's stop of `replay` before it moves on. */
export function autoplayDelayMs(
    replay: { readonly events: readonly StepEvent[]; readonly navigation: NavigationIndex },
    cursor: ReplayCursor,
): number {
    const move = replay.events[replay.navigation.stops[cursor.stop].moveEntry]?.type;
    const share = move === undefined ? 1 : (STOP_SHARE[move] ?? 1);
    return STOP_MS * share;
}

/** Autoplay's next move from the cursor and whether it pauses there; null where it cannot go on. */
export function autoplayStep(
    nav: NavigationIndex,
    cursor: ReplayCursor,
): { readonly cursor: ReplayCursor; readonly pause: boolean } | null {
    const next = nextCursor(nav, cursor);
    return next === null ? null : { cursor: next, pause: isPauseStop(nav, next) };
}

/**
 * How long observe autoplay shows the cursor's stop before it moves on: each page of a round's result for
 * `OBSERVE_RESULT_HOLD_MS`, any other stop as a replay's autoplay does.
 */
export function observeAutoplayDelayMs(
    replay: { readonly events: readonly StepEvent[]; readonly navigation: NavigationIndex },
    cursor: ReplayCursor,
): number {
    return isResultStop(replay.navigation, cursor)
        ? OBSERVE_RESULT_HOLD_MS
        : autoplayDelayMs(replay, cursor);
}
