import { type KanDeclaredEvent } from "@/entities/table";
import { type ReplayLine } from "@/shared/protocol";

import { traceGameClient } from "./dispatch";
import { type ClientEffect, type ClientEvent, type GameClientState } from "./types";

/**
 * One step of a timeline: its event with what the step took of it, as parsed, the state after it and the effects it
 * described.
 */
export interface TimelineEntry {
    readonly event: ClientEvent;
    readonly parsed: ReplayLine | KanDeclaredEvent | null;
    readonly state: GameClientState;
    readonly effects: readonly ClientEffect[];
}

/**
 * The client states a sequence of events yields, from any source: an entry per event, but one per part of an event
 * the dispatcher takes in parts (a replay's round end that robbed a kan: the kan declared, then the result). Stepping
 * back selects an earlier state, never an inverse event; nothing here executes an effect, so revisiting a state sends
 * nothing and arms no timer.
 */
export interface ClientTimeline {
    readonly start: GameClientState;
    readonly entries: readonly TimelineEntry[];
}

export function buildClientTimeline(
    start: GameClientState,
    events: readonly ClientEvent[],
): ClientTimeline {
    const entries: TimelineEntry[] = [];
    let state = start;
    for (const event of events) {
        for (const step of traceGameClient(state, event)) {
            entries.push({ effects: step.effects, event, parsed: step.parsed, state: step.state });
            ({ state } = step);
        }
    }
    return { entries, start };
}

/** Every state of the timeline: the start at 0, then the state after each entry, so index i+1 follows entry i. */
export function timelineStates(timeline: ClientTimeline): readonly GameClientState[] {
    return [timeline.start, ...timeline.entries.map((entry) => entry.state)];
}
