import { CALL_TYPE } from "@/shared/protocol";

import { decisionOf, roundConfirmOf, startConfirmOf } from "./pending";
import { type Decision, type LiveClient } from "./types";

/** The countdown's display step: it shows whole seconds left. */
const COUNTDOWN_STEP_MS = 1000;

/**
 * The move that awaits the viewer: its own turn, a call on a discard, a ron that robs a kan, a result's confirm, or the
 * game start's.
 */
type DecisionMove = "turn" | "call" | "chankan" | "result" | "start";

/**
 * A decision's time as the server runs it, in whole seconds (rounded up): its base time first, then its bank, which drains
 * only once the base ran out. In the bank the base reads 0 and the bank is the time left.
 */
export interface DecisionClock {
    readonly inBank: boolean;
    readonly baseSeconds: number;
    readonly bankSeconds: number;
}

/**
 * Where the move awaiting the viewer stands at the state's logical `now`: running with the whole seconds left to its
 * deadline (rounded up, so it reads 1 until the deadline) and its base and bank apart; open with no
 * deadline to count down to; or past its deadline.
 */
export type DecisionCountdown =
    | {
          readonly kind: "running";
          readonly move: DecisionMove;
          readonly secondsLeft: number;
          readonly clock: DecisionClock | null;
      }
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

function decisionClock(decision: Decision, deadline: number, now: number): DecisionClock | null {
    if (decision.baseDeadline === null) {
        return null;
    }
    const { baseDeadline } = decision;
    if (now >= baseDeadline) {
        return { bankSeconds: secondsLeft(deadline, now), baseSeconds: 0, inBank: true };
    }
    return {
        bankSeconds: secondsLeft(deadline, baseDeadline),
        baseSeconds: secondsLeft(baseDeadline, now),
        inBank: false,
    };
}

/** The countdown of the viewer's unanswered decision, read from the state's `now`; null with none awaiting it. */
export function decisionCountdown(state: LiveClient): DecisionCountdown | null {
    const decision = decisionOf(state);
    if (decision === null || decision.status.kind === "submitted") {
        return null;
    }
    const move = decisionMove(decision);
    if (decision.status.kind === "expired") {
        return { kind: "expired", move };
    }
    const { deadline } = decision;
    if (deadline === null) {
        return { kind: "untimed", move };
    }
    return {
        clock: decisionClock(decision, deadline, state.now),
        kind: "running",
        move,
        secondsLeft: secondsLeft(deadline, state.now),
    };
}

/** The deadline of the round confirm (a result's or the start's) the viewer owes or sent; null otherwise or unknown. */
function roundConfirmDeadline(state: LiveClient): number | null {
    const roundConfirm = roundConfirmOf(state);
    return roundConfirm?.kind === "owed" || roundConfirm?.kind === "sent"
        ? roundConfirm.deadline
        : null;
}

/**
 * The countdown to the server's round advance of the round result, or to its start confirm's timeout, the viewer owes
 * a confirm or waits on after sending it, read from the state's `now`; null otherwise. Past its deadline it shows as
 * expired, for display only.
 */
export function roundConfirmCountdown(state: LiveClient): DecisionCountdown | null {
    const roundConfirm = roundConfirmOf(state);
    if (roundConfirm?.kind !== "owed" && roundConfirm?.kind !== "sent") {
        return null;
    }
    const move = startConfirmOf(state) === null ? "result" : "start";
    const deadline = roundConfirmDeadline(state);
    if (deadline === null) {
        return { kind: "untimed", move };
    }
    if (state.now >= deadline) {
        return { kind: "expired", move };
    }
    return { clock: null, kind: "running", move, secondsLeft: secondsLeft(deadline, state.now) };
}

/** The countdown of what awaits the viewer now: its unanswered decision, else a round result it owes a confirm. */
export function pendingCountdown(state: LiveClient): DecisionCountdown | null {
    const decision = decisionCountdown(state);
    if (decision !== null || roundConfirmOf(state)?.kind !== "owed") {
        return decision;
    }
    return roundConfirmCountdown(state);
}

/**
 * The whole seconds left on the opening screen showing, rounded up: the resume screen's own time, the start screen's
 * start confirm's (0 once past its deadline, as the server times it out); null while none shows, the resume screen's
 * time ran out, or the start screen counts no confirm.
 */
export function openingCountdown(state: LiveClient): number | null {
    const { now, opening } = state;
    if (opening.kind !== "showing") {
        return null;
    }
    if (opening.cause === "resume") {
        return now < opening.until ? secondsLeft(opening.until, now) : null;
    }
    const countdown = roundConfirmCountdown(state);
    if (countdown?.kind === "running") {
        return countdown.secondsLeft;
    }
    return countdown?.kind === "expired" ? 0 : null;
}

/** The logical time `seconds` (as shown, counting down to `deadline`) next changes. */
function nextShownChange(deadline: number, seconds: number): number {
    return deadline - (seconds - 1) * COUNTDOWN_STEP_MS;
}

/** When a decision's base time runs out, or null without a timed decision. */
function decisionBaseDeadline(decision: Decision | null): number | null {
    return decision?.baseDeadline ?? null;
}

/** Every time a running countdown next shows a different number: its seconds left and, in a decision's base, the base's. */
function countdownChanges(countdown: DecisionCountdown | null, state: LiveClient): number[] {
    if (countdown?.kind !== "running") {
        return [];
    }
    const deadline =
        countdown.move === "result" || countdown.move === "start"
            ? roundConfirmDeadline(state)
            : (decisionOf(state)?.deadline ?? null);
    if (deadline === null) {
        return [];
    }
    const changes = [nextShownChange(deadline, countdown.secondsLeft)];
    const baseDeadline = decisionBaseDeadline(decisionOf(state));
    if (countdown.clock !== null && !countdown.clock.inBank && baseDeadline !== null) {
        changes.push(nextShownChange(baseDeadline, countdown.clock.baseSeconds));
    }
    return changes;
}

/**
 * The logical time a running countdown (the decision's, else the round confirm's, and the resume screen's) next shows
 * a different number, for the live driver to tick at, so the countdown moves with `now` rather than the wall clock;
 * null when none runs.
 */
export function nextCountdownChange(state: LiveClient): number | null {
    const decision = decisionCountdown(state);
    const shown = decision ?? roundConfirmCountdown(state);
    const changes = countdownChanges(shown, state);
    const { opening } = state;
    const seconds = openingCountdown(state);
    if (opening.kind === "showing" && opening.cause === "resume" && seconds !== null) {
        changes.push(nextShownChange(opening.until, seconds));
    }
    return changes.length === 0 ? null : Math.min(...changes);
}
