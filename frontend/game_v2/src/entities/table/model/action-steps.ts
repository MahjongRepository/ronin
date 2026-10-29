import { type KanDeclaredEvent, type ReplayEvent } from "./types";

/**
 * The replay event of each timeline entry, the kan a round end's win robbed as declared before it, or null for an
 * entry that moves no step: a seat control line or a line that did not parse. A null entry folds into the next step,
 * so a seat's AI replacement shows from the move after it.
 */
export type StepEvent = ReplayEvent | KanDeclaredEvent | null;

type ShownEvent = NonNullable<StepEvent>;

export interface ActionStep {
    /** Timeline state index of the primary stopping event (used for lastEventDescription).
     *  For non-batched steps this equals stateIndex. For batched steps (e.g., kan + dora_revealed),
     *  this points to the stopping event's state so the description shows "called kan" not "new dora". */
    readonly descriptionStateIndex: number;
    /** Timeline state index to display (includes trailing non-stopping events like dora_revealed) */
    readonly stateIndex: number;
}

const TRAILING_TYPES: ReadonlySet<ShownEvent["type"]> = new Set(["dora_revealed", "game_started"]);

/** The replay event before index `at`, skipping the entries that move no step. */
function previousEvent(events: readonly StepEvent[], at: number): ShownEvent | null {
    for (let index = at - 1; index >= 0; index--) {
        const event = events[index];
        if (event !== null) {
            return event;
        }
    }
    return null;
}

/** Whether the event at `at` folds into the step before it: bookkeeping, or the round's first draw. */
function isTrailing(events: readonly StepEvent[], at: number): boolean {
    const event = events[at];
    if (event === null) {
        return false;
    }
    if (TRAILING_TYPES.has(event.type)) {
        return true;
    }
    return event.type === "draw" && previousEvent(events, at)?.type === "round_started";
}

function isStoppingEvent(events: readonly StepEvent[], at: number): boolean {
    return events[at] !== null && !isTrailing(events, at);
}

/** Scans ahead past any trailing events starting from `start`, returns the end index. */
function findBatchEnd(events: readonly StepEvent[], start: number): number {
    let end = start;
    while (end < events.length && isTrailing(events, end)) {
        end++;
    }
    return end;
}

/** Collects action steps by scanning events for stopping points and batching trailing events. */
function collectStoppingSteps(events: readonly StepEvent[], steps: ActionStep[]): void {
    let i = 0;
    while (i < events.length) {
        if (!isStoppingEvent(events, i)) {
            i++;
        } else {
            const descriptionStateIndex = i + 1;
            const end = findBatchEnd(events, i + 1);
            steps.push({ descriptionStateIndex, stateIndex: end });
            i = end;
        }
    }
}

/**
 * Maps timeline entries to "action step" indices, skipping bookkeeping events.
 *
 * Each action step is a stop point in the replay navigation. Trailing events (like dora_revealed) are batched with
 * the preceding stopping event: the display state advances past them, but the description state stays on the
 * stopping event. Entries that move no step are shown from the next step on.
 *
 * Returns an array where the first entry is always the initial state (before any events)
 * and the last entry's stateIndex equals events.length (the state after all events).
 */
export function buildActionSteps(events: readonly StepEvent[]): ActionStep[] {
    const initialEnd = findBatchEnd(events, 0);
    const steps: ActionStep[] = [{ descriptionStateIndex: initialEnd, stateIndex: initialEnd }];
    collectStoppingSteps(events, steps);

    if (events.length > 0 && steps[steps.length - 1].stateIndex < events.length) {
        steps.push({ descriptionStateIndex: events.length, stateIndex: events.length });
    }

    return steps;
}
