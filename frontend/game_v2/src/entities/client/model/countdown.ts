import { CALL_TYPE } from "@/shared/protocol";

import { type Decision, type GameClientState } from "./types";

/** The countdown's display step: it shows whole seconds left. */
const COUNTDOWN_STEP_MS = 1000;

/** The move that awaits the viewer: its own turn, a call on a discard, a ron that robs a kan, or a result's confirm. */
type DecisionMove = "turn" | "call" | "chankan" | "result";

/**
 * Where the move awaiting the viewer stands at the state's logical `now`: running with the whole seconds left
 * (rounded up, so it reads 1 until the deadline), open with no deadline to count down to, or past its deadline.
 */
export type DecisionCountdown =
    | { readonly kind: "running"; readonly move: DecisionMove; readonly secondsLeft: number }
    | { readonly kind: "untimed" | "expired"; readonly move: DecisionMove };

function decisionMove(decision: Decision): DecisionMove {
    if (decision.kind === "call" && decision.callType === CALL_TYPE.CHANKAN) {
        return "chankan";
    }
    return decision.kind;
}

function secondsLeft(deadline: number, now: number): number {
    return Math.ceil(Math.max(0, deadline - now) / COUNTDOWN_STEP_MS);
}

/** The countdown of the viewer's unanswered decision, read from the state's `now`; null with none awaiting it. */
export function decisionCountdown(state: GameClientState): DecisionCountdown | null {
    const { decision, now } = state;
    if (decision === null || decision.status.kind === "submitted") {
        return null;
    }
    const move = decisionMove(decision);
    if (decision.status.kind === "expired") {
        return { kind: "expired", move };
    }
    if (decision.deadline === null) {
        return { kind: "untimed", move };
    }
    return { kind: "running", move, secondsLeft: secondsLeft(decision.deadline, now) };
}

/** The round advance deadline of a round result the viewer owes or sent a confirm; null otherwise or unknown. */
function roundConfirmDeadline({ roundConfirm }: GameClientState): number | null {
    return roundConfirm?.kind === "owed" || roundConfirm?.kind === "sent"
        ? roundConfirm.deadline
        : null;
}

/**
 * The countdown to the server's round advance of the round result the viewer owes a confirm or waits on after
 * sending it, read from the state's `now`; null otherwise. Past its deadline it shows as expired, for display only.
 */
export function roundConfirmCountdown(state: GameClientState): DecisionCountdown | null {
    const { now, roundConfirm } = state;
    if (roundConfirm?.kind !== "owed" && roundConfirm?.kind !== "sent") {
        return null;
    }
    const move = "result";
    const deadline = roundConfirmDeadline(state);
    if (deadline === null) {
        return { kind: "untimed", move };
    }
    if (now >= deadline) {
        return { kind: "expired", move };
    }
    return { kind: "running", move, secondsLeft: secondsLeft(deadline, now) };
}

/** The countdown of what awaits the viewer now: its unanswered decision, else a round result it owes a confirm. */
export function pendingCountdown(state: GameClientState): DecisionCountdown | null {
    const decision = decisionCountdown(state);
    if (decision !== null || state.roundConfirm?.kind !== "owed") {
        return decision;
    }
    return roundConfirmCountdown(state);
}

function nextChange(countdown: DecisionCountdown | null, deadline: number | null): number | null {
    if (countdown?.kind !== "running" || deadline === null) {
        return null;
    }
    return deadline - (countdown.secondsLeft - 1) * COUNTDOWN_STEP_MS;
}

/**
 * The logical time a running countdown (the decision's, else the round advance's) next shows a different number, for
 * the live driver to tick at, so the countdown moves with `now` rather than the wall clock; null when none runs.
 */
export function nextCountdownChange(state: GameClientState): number | null {
    const decision = decisionCountdown(state);
    if (decision !== null) {
        return nextChange(decision, state.decision?.deadline ?? null);
    }
    return nextChange(roundConfirmCountdown(state), roundConfirmDeadline(state));
}
