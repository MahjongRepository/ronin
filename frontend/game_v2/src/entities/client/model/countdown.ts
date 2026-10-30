import { CALL_TYPE } from "@/shared/protocol";

import { decisionOf, roundConfirmOf } from "./pending";
import { type Decision, type LiveClient } from "./types";

/** The countdown's display step: it shows whole seconds left. */
const COUNTDOWN_STEP_MS = 1000;

/** The move that awaits the viewer: its own turn, a call on a discard, a ron that robs a kan, or a result's confirm. */
type DecisionMove = "turn" | "call" | "chankan" | "result";

/**
 * A turn's time as the server runs it, in whole seconds (rounded up): its base time first, then its bank, which drains
 * only once the base ran out. In the bank the base reads 0 and the bank is the time left.
 */
export interface TurnClock {
    readonly inBank: boolean;
    readonly baseSeconds: number;
    readonly bankSeconds: number;
}

/**
 * Where the move awaiting the viewer stands at the state's logical `now`: running with the whole seconds left to its
 * deadline (rounded up, so it reads 1 until the deadline) and, for a turn, its base and bank apart; open with no
 * deadline to count down to; or past its deadline.
 */
export type DecisionCountdown =
    | {
          readonly kind: "running";
          readonly move: DecisionMove;
          readonly secondsLeft: number;
          readonly turn: TurnClock | null;
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

function turnClock(decision: Decision, deadline: number, now: number): TurnClock | null {
    if (decision.kind !== "turn" || decision.baseDeadline === null) {
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
        kind: "running",
        move,
        secondsLeft: secondsLeft(deadline, state.now),
        turn: turnClock(decision, deadline, state.now),
    };
}

/** The round advance deadline of a round result the viewer owes or sent a confirm; null otherwise or unknown. */
function roundConfirmDeadline(state: LiveClient): number | null {
    const roundConfirm = roundConfirmOf(state);
    return roundConfirm?.kind === "owed" || roundConfirm?.kind === "sent"
        ? roundConfirm.deadline
        : null;
}

/**
 * The countdown to the server's round advance of the round result the viewer owes a confirm or waits on after
 * sending it, read from the state's `now`; null otherwise. Past its deadline it shows as expired, for display only.
 */
export function roundConfirmCountdown(state: LiveClient): DecisionCountdown | null {
    const roundConfirm = roundConfirmOf(state);
    if (roundConfirm?.kind !== "owed" && roundConfirm?.kind !== "sent") {
        return null;
    }
    const move = "result";
    const deadline = roundConfirmDeadline(state);
    if (deadline === null) {
        return { kind: "untimed", move };
    }
    if (state.now >= deadline) {
        return { kind: "expired", move };
    }
    return { kind: "running", move, secondsLeft: secondsLeft(deadline, state.now), turn: null };
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
 * The whole seconds left of the server's game start pause while the table waits for its first deal, rounded up; null
 * before the game starts, once it deals, with no pause known, or once the pause ran out ahead of the deal.
 */
export function firstDealCountdown(state: LiveClient): number | null {
    const { firstDealDue, now, table } = state;
    if (table.phase !== "pre_game" || firstDealDue === null || now >= firstDealDue) {
        return null;
    }
    return secondsLeft(firstDealDue, now);
}

/** The logical time `seconds` (as shown, counting down to `deadline`) next changes. */
function nextShownChange(deadline: number, seconds: number): number {
    return deadline - (seconds - 1) * COUNTDOWN_STEP_MS;
}

/** When a turn's base time runs out, or null for a turn without a deadline, a call or no decision. */
function turnBaseDeadline(decision: Decision | null): number | null {
    return decision?.kind === "turn" ? decision.baseDeadline : null;
}

/** Every time a running countdown next shows a different number: its seconds left and, in a turn's base, the base's. */
function countdownChanges(countdown: DecisionCountdown | null, state: LiveClient): number[] {
    if (countdown?.kind !== "running") {
        return [];
    }
    const deadline =
        countdown.move === "result"
            ? roundConfirmDeadline(state)
            : (decisionOf(state)?.deadline ?? null);
    if (deadline === null) {
        return [];
    }
    const changes = [nextShownChange(deadline, countdown.secondsLeft)];
    const baseDeadline = turnBaseDeadline(decisionOf(state));
    if (countdown.turn !== null && !countdown.turn.inBank && baseDeadline !== null) {
        changes.push(nextShownChange(baseDeadline, countdown.turn.baseSeconds));
    }
    return changes;
}

/**
 * The logical time a running countdown (the decision's, else the round advance's, and the game start pause's) next
 * shows a different number, for the live driver to tick at, so the countdown moves with `now` rather than the wall
 * clock; null when none runs.
 */
export function nextCountdownChange(state: LiveClient): number | null {
    const decision = decisionCountdown(state);
    const shown = decision ?? roundConfirmCountdown(state);
    const changes = countdownChanges(shown, state);
    const firstDeal = firstDealCountdown(state);
    if (firstDeal !== null && state.firstDealDue !== null) {
        changes.push(nextShownChange(state.firstDealDue, firstDeal));
    }
    return changes.length === 0 ? null : Math.min(...changes);
}
