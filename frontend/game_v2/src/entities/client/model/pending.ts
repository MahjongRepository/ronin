import { type Decision, type LiveClient, type Pending, type RoundConfirm } from "./types";

/** What the seat owes the server: nothing out of step, else what its in-step state holds. */
export function pendingOf(state: LiveClient): Pending | null {
    return state.sync.kind === "in_step" ? state.sync.pending : null;
}

/** The viewer's open decision, or null while it owes none. */
export function decisionOf(state: LiveClient): Decision | null {
    const pending = pendingOf(state);
    return pending?.kind === "decision" ? pending.decision : null;
}

/** Where the viewer stands with the round result it reads before the next deal, or null while it reads none. */
export function roundConfirmOf(state: LiveClient): RoundConfirm | null {
    const pending = pendingOf(state);
    return pending?.kind === "round_confirm" ? pending.confirm : null;
}

/**
 * The client with what the seat owes replaced. Out of step it owes nothing, so only clearing it is taken there: a
 * client that tries to owe something out of step is a bug, thrown.
 */
export function withPending(state: LiveClient, pending: Pending | null): LiveClient {
    if (state.sync.kind === "in_step") {
        return state.sync.pending === pending
            ? state
            : { ...state, sync: { kind: "in_step", pending } };
    }
    if (pending !== null) {
        throw new Error(`An out-of-step client owes nothing, given a ${pending.kind}`);
    }
    return state;
}

export function replaceDecision(state: LiveClient, decision: Decision | null): LiveClient {
    return withPending(state, decision === null ? null : { decision, kind: "decision" });
}

export function replaceRoundConfirm(state: LiveClient, confirm: RoundConfirm | null): LiveClient {
    return withPending(state, confirm === null ? null : { confirm, kind: "round_confirm" });
}

/**
 * The client after a step, owing only while its session holds the seat: an open decision and a round confirm both go
 * once the session plays no more (a dropped socket, an end, or never admitted yet), since only a held seat answers and
 * the server, admitting the seat again, re-sends every wait it still owes and its snapshot says whether the confirm is.
 */
export function settledPending(state: LiveClient): LiveClient {
    return state.session.status === "playing" ? state : withPending(state, null);
}
