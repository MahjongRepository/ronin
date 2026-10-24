import { applyEvent } from "./apply-event";
import { createInitialTableState } from "./initial-state";
import { type ReplayEvent, type TableState } from "./types";

/**
 * Pre-computes all game states from a replay event sequence.
 *
 * Returns an array where states[0] is the initial state (before any events),
 * and states[i+1] is the state after applying events[i].
 * Length is always events.length + 1.
 */
export function buildTimeline(events: ReplayEvent[]): TableState[] {
    const states: TableState[] = [createInitialTableState()];

    for (const event of events) {
        const previousState = states[states.length - 1];
        states.push(applyEvent(previousState, event));
    }

    return states;
}
