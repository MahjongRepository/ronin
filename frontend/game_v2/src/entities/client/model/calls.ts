import {
    CALLOUT_MS,
    type Call,
    type TableEvent,
    type TableState,
    callsShownKan,
    eventCalls,
} from "@/entities/table";

import { snapshotLeftHand } from "./play-switches";
import { type LiveClient, type ReplayClient, type ShownCalls } from "./types";

function shownCalls(calls: readonly Call[], at: number): ShownCalls {
    return { at, calls, until: at + CALLOUT_MS };
}

/**
 * The calls a live board shows after a server message's table event, from the table it found (`state`'s) to the one it
 * left: the calls the event makes, but a kan the calls still showing call already (the declaration a reconnect's re-sent prompt repeats); else
 * those still showing, which only their time ends, since a move that calls nothing may follow a call at once (an AI
 * player's discard after its pon, the viewer's own draw after a riichi). A deal, or a snapshot that leaves the hand,
 * starts a new board, which shows none of the hand before, however soon it follows that hand's last call.
 */
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
    const shown = state.calls;
    const live = shown !== null && shown.until > state.now ? shown.calls : [];
    const calls = (eventCalls(event, state.table, table) ?? []).filter(
        (call) => !callsShownKan(live, call),
    );
    return calls.length === 0 ? shown : shownCalls(calls, state.now);
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
    const calls = eventCalls(event, state.table, table);
    if (calls === null) {
        return state.calls;
    }
    return calls.length === 0 ? null : shownCalls(calls, state.now);
}

/** The calls shown at logical time `at`: none once their time is past. */
export function callsAt(calls: ShownCalls | null, at: number): ShownCalls | null {
    return calls !== null && at >= calls.until ? null : calls;
}
