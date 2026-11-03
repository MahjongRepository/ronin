import {
    CALLOUT_MS,
    type Call,
    type TableEvent,
    type TableState,
    callsShownKan,
    eventCalls,
} from "@/entities/table";
import { tileType } from "@/shared/protocol";

import { decisionOf } from "./pending";
import { snapshotLeftHand } from "./play-switches";
import {
    type DecisionIntent,
    type LiveClient,
    type PlaySwitch,
    type ReplayClient,
    type ShownCalls,
} from "./types";

/** Keep the existing window for a delayed server result to open after a locally declared win. */
export const WIN_CALLOUT_CONTEXT_MS = 3000;

function shownCalls(calls: readonly Call[], at: number): ShownCalls {
    const wins = calls.some((call) => call.kind === "ron" || call.kind === "tsumo");
    return { at, calls, until: at + (wins ? WIN_CALLOUT_CONTEXT_MS : CALLOUT_MS) };
}

function intentCall(intent: DecisionIntent, seat: number | null): Call | null {
    if (intent.type !== "choose" || intent.offer.kind === "kyuushu" || seat === null) {
        return null;
    }
    const { offer } = intent;
    return offer.kind === "kan"
        ? { kanTileType: tileType(offer.tileId), kind: offer.kind, seat }
        : { kind: offer.kind, seat };
}

export function submittedCall(state: LiveClient): Call | null {
    const status = decisionOf(state)?.status;
    return status?.kind === "submitted" ? intentCall(status.intent, state.viewerSeat) : null;
}

export function matchesCall(call: Call, other: Call | null): boolean {
    return (
        call.kind === other?.kind &&
        call.seat === other.seat &&
        call.kanTileType === other.kanTileType
    );
}

export function declareIntent(
    state: LiveClient,
    intent: DecisionIntent,
    bySwitch: PlaySwitch | null,
): ShownCalls | null {
    const call = intentCall(intent, state.viewerSeat);
    if (call === null) {
        return state.calls;
    }
    const simultaneous =
        bySwitch !== null && state.calls?.at === state.now
            ? state.calls.calls.filter((other) => other.seat !== call.seat)
            : [];
    return shownCalls([...simultaneous, call], state.now);
}

/**
 * The calls a live board shows after a server message's table event, from the table it found (`state`'s) to the one it
 * left: new declarations, excluding a lone echo of the submitted intent and a kan already showing; else
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
    const declared = submittedCall(state);
    return calls.every((call) => matchesCall(call, declared))
        ? shown
        : shownCalls(calls, state.now);
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
