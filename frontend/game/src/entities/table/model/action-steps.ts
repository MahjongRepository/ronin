import { type ReplayEvent } from "./types";

export interface ActionStep {
    /** Timeline state index of the primary stopping event (used for lastEventDescription).
     *  For non-batched steps this equals stateIndex. For batched steps (e.g., kan + dora_revealed),
     *  this points to the stopping event's state so the description shows "called kan" not "new dora". */
    descriptionStateIndex: number;
    /** Timeline state index to display (includes trailing non-stopping events like dora_revealed) */
    stateIndex: number;
}

const NON_STOPPING_TYPES: ReadonlySet<ReplayEvent["type"]> = new Set([
    "dora_revealed",
    "game_started",
]);

function isStoppingEvent(event: ReplayEvent, previousEvent: ReplayEvent | undefined): boolean {
    if (NON_STOPPING_TYPES.has(event.type)) {
        return false;
    }
    // First draw after round_started is batched so the round starts with a drawn tile
    if (event.type === "draw" && previousEvent?.type === "round_started") {
        return false;
    }
    return true;
}

/** Scans ahead past any trailing non-stopping events starting from `start`, returns the end index. */
function findBatchEnd(events: ReplayEvent[], start: number): number {
    let end = start;
    while (end < events.length && !isStoppingEvent(events[end], events[end - 1])) {
        end++;
    }
    return end;
}

/** Collects action steps by scanning events for stopping points and batching trailing non-stopping events. */
function collectStoppingSteps(events: ReplayEvent[], steps: ActionStep[]): void {
    let i = 0;
    while (i < events.length) {
        if (!isStoppingEvent(events[i], events[i - 1])) {
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
 * Maps raw event indices to "action step" indices, skipping bookkeeping events.
 *
 * Each action step is a stop point in the replay navigation. Non-stopping events
 * (like dora_revealed) are batched with the preceding stopping event: the display
 * state advances past them, but the description state stays on the stopping event.
 *
 * Returns an array where the first entry is always the initial state (before any events)
 * and the last entry's stateIndex equals events.length (the state after all events).
 */
export function buildActionSteps(events: ReplayEvent[]): ActionStep[] {
    const initialEnd = findBatchEnd(events, 0);
    const steps: ActionStep[] = [{ descriptionStateIndex: initialEnd, stateIndex: initialEnd }];
    collectStoppingSteps(events, steps);

    // Ensure the terminal state is reachable when all events are non-stopping
    if (events.length > 0 && steps[steps.length - 1].stateIndex < events.length) {
        steps.push({ descriptionStateIndex: events.length, stateIndex: events.length });
    }

    return steps;
}
