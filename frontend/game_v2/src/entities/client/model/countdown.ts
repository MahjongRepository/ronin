import { type Decision, type GameClientState } from "./types";

/** The countdown's display step: it shows whole seconds left. */
const COUNTDOWN_STEP_MS = 1000;

/**
 * Where the viewer's unanswered decision (its own turn or a call) stands at the state's logical `now`: running with
 * the whole seconds left (rounded up, so it reads 1 until the deadline), open with no deadline to count down to,
 * or past its deadline.
 */
export type DecisionCountdown =
    | { readonly kind: "running"; readonly move: Decision["kind"]; readonly secondsLeft: number }
    | { readonly kind: "untimed" | "expired"; readonly move: Decision["kind"] };

/** The countdown of the viewer's unanswered decision, read from the state's `now`; null with none awaiting it. */
export function decisionCountdown(state: GameClientState): DecisionCountdown | null {
    const { decision, now } = state;
    if (decision === null || decision.status.kind === "submitted") {
        return null;
    }
    const move = decision.kind;
    if (decision.status.kind === "expired") {
        return { kind: "expired", move };
    }
    if (decision.deadline === null) {
        return { kind: "untimed", move };
    }
    const secondsLeft = Math.ceil(Math.max(0, decision.deadline - now) / COUNTDOWN_STEP_MS);
    return { kind: "running", move, secondsLeft };
}

/**
 * The logical time the running countdown next shows a different number, for the live driver to tick at, so the
 * countdown moves with `now` rather than the wall clock; null when no countdown runs.
 */
export function nextCountdownChange(state: GameClientState): number | null {
    const countdown = decisionCountdown(state);
    const deadline = state.decision?.deadline ?? null;
    if (countdown?.kind !== "running" || deadline === null) {
        return null;
    }
    return deadline - (countdown.secondsLeft - 1) * COUNTDOWN_STEP_MS;
}
