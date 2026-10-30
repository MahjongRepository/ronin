import { type StepEvent } from "./action-steps";
import { type NavigationIndex } from "./navigation-index";
import { type ReplayCursor, nextCursor } from "./replay-cursor";

/** Autoplay's speeds, as multiples of its pace at 1x. */
export const AUTOPLAY_SPEEDS = [0.5, 1, 2, 4] as const;

export type AutoplaySpeed = (typeof AUTOPLAY_SPEEDS)[number];

/** Whether autoplay runs, and at what speed: a view's state, which the speed outlives. */
export interface AutoplayState {
    readonly playing: boolean;
    readonly speed: AutoplaySpeed;
}

/** How long a stop shows at 1x before autoplay moves on. */
const STOP_MS = 800;

/** A stop's share of `STOP_MS` by its move: a deal is read longer, a draw only leads to its discard. */
const STOP_SHARE: Partial<Readonly<Record<StepEvent["type"], number>>> = {
    draw: 0.5,
    round_started: 2,
};

/** The speed after `speed` in `AUTOPLAY_SPEEDS`, from the fastest back to the slowest. */
export function nextAutoplaySpeed(speed: AutoplaySpeed): AutoplaySpeed {
    return AUTOPLAY_SPEEDS[(AUTOPLAY_SPEEDS.indexOf(speed) + 1) % AUTOPLAY_SPEEDS.length];
}

/** The speed a stored number names, or 1x for one that names none. */
export function autoplaySpeedOf(value: number): AutoplaySpeed {
    return AUTOPLAY_SPEEDS.find((speed) => speed === value) ?? 1;
}

/**
 * Whether a continuous move (autoplay, a held button or key, a turning wheel) pauses at the cursor: on any page of a
 * round's result, and at the replay's last stop, so a result is read before the next deal.
 */
export function isPauseStop(nav: NavigationIndex, cursor: ReplayCursor): boolean {
    const { round } = nav.stops[cursor.stop];
    return nav.rounds[round].resultStop === cursor.stop || cursor.stop === nav.stops.length - 1;
}

/** How long autoplay shows the cursor's stop of `replay` before it moves on, at `speed`. */
export function autoplayDelayMs(
    replay: { readonly events: readonly StepEvent[]; readonly navigation: NavigationIndex },
    cursor: ReplayCursor,
    speed: AutoplaySpeed,
): number {
    const move = replay.events[replay.navigation.stops[cursor.stop].moveEntry]?.type;
    const share = move === undefined ? 1 : (STOP_SHARE[move] ?? 1);
    return (STOP_MS * share) / speed;
}

/** Autoplay's next move from the cursor and whether it pauses there; null where it cannot go on. */
export function autoplayStep(
    nav: NavigationIndex,
    cursor: ReplayCursor,
): { readonly cursor: ReplayCursor; readonly pause: boolean } | null {
    const next = nextCursor(nav, cursor);
    return next === null ? null : { cursor: next, pause: isPauseStop(nav, next) };
}
