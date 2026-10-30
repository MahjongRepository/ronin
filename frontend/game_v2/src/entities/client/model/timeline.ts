import { type KanDeclaredEvent } from "@/entities/table";
import { type ReplayLine } from "@/shared/protocol";

import { traceLiveClient } from "./dispatch";
import {
    type ClientEffect,
    type ClientEvent,
    type GameClientState,
    type LiveClient,
    type LiveEvent,
} from "./types";

/**
 * One step of a timeline: its event with what the step took of it, as parsed, the state after it and the effects it
 * described.
 */
export interface TimelineEntry<State extends GameClientState = GameClientState> {
    readonly event: ClientEvent;
    readonly parsed: ReplayLine | KanDeclaredEvent | null;
    readonly state: State;
    readonly effects: readonly ClientEffect[];
}

/**
 * The client states a sequence of events yields, from any source: an entry per event, but one per part of an event
 * the dispatcher takes in parts (a replay's round end that robbed a kan: the kan declared, then the result). Stepping
 * back selects an earlier state, never an inverse event; nothing here executes an effect, so revisiting a state sends
 * nothing and arms no timer.
 */
export interface ClientTimeline<State extends GameClientState = GameClientState> {
    readonly start: State;
    readonly entries: readonly TimelineEntry<State>[];
}

/** The timeline a live client's events yield from `start`. */
export function buildClientTimeline(
    start: LiveClient,
    events: readonly LiveEvent[],
): ClientTimeline<LiveClient> {
    const entries: TimelineEntry<LiveClient>[] = [];
    let state = start;
    for (const event of events) {
        for (const step of traceLiveClient(state, event)) {
            entries.push({ effects: step.effects, event, parsed: step.parsed, state: step.state });
            ({ state } = step);
        }
    }
    return { entries, start };
}

/** Every state of the timeline: the start at 0, then the state after each entry, so index i+1 follows entry i. */
export function timelineStates<State extends GameClientState>(
    timeline: ClientTimeline<State>,
): readonly State[] {
    return [timeline.start, ...timeline.entries.map((entry) => entry.state)];
}
