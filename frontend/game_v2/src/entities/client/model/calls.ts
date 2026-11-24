import {
    CALLOUT_MS,
    type Call,
    type TableEvent,
    type TableState,
    eventCalls,
} from "@/entities/table";

import { snapshotLeftHand } from "./play-switches";
import { type LiveClient, type ReplayClient, type ShownCalls } from "./types";

function shownCalls(calls: readonly Call[], at: number): ShownCalls {
    return { calls, until: at + CALLOUT_MS };
}

export function liveCalls(
    state: LiveClient,
    event: TableEvent,
    table: TableState,
): ShownCalls | null {
    const newBoard =
        event.type === "round_started" ||
        (event.type === "game_reconnected" && snapshotLeftHand(state.table, table));
    if (newBoard) {
        return null;
    }
    const calls = eventCalls(event, table);
    return calls?.length ? shownCalls(calls, state.now) : state.calls;
}

/**
 * The calls a replay's board shows after a line's table event: the calls a move makes, none for a move that makes
 * none, and those of the move before for its bookkeeping and annotations, so each stop shows its own move's calls.
 */
export function replayCalls(
    state: ReplayClient,
    event: TableEvent,
    table: TableState,
): ShownCalls | null {
    const calls = eventCalls(event, table);
    if (calls === null) {
        return state.calls;
    }
    return calls.length === 0 ? null : shownCalls(calls, state.now);
}

/** The calls shown at logical time `at`: none once their time is past. */
export function callsAt(calls: ShownCalls | null, at: number): ShownCalls | null {
    return calls !== null && at >= calls.until ? null : calls;
}
