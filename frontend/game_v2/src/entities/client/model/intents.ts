import { hasEnded, holdsSeat } from "@/entities/session";
import { type PlayerState } from "@/entities/table";
import { type ClientMessage } from "@/shared/protocol";

import { answerDecision, offerAnswer } from "./decision";
import { decisionOf, replaceDecision } from "./pending";
import { switchAnswer, unseenWait } from "./play-switches";
import { confirmStep, reopenResultStep } from "./round-confirm";
import {
    type ClientStep,
    type DecisionIntent,
    type LiveClient,
    type PlayIntent,
    type PlaySwitch,
} from "./types";

/**
 * Whether the client may answer what its seat owes: its session holds the seat. Out of step the seat owes nothing,
 * so it answers nothing.
 */
export function canAnswer(state: LiveClient): boolean {
    return holdsSeat(state.session);
}

function viewerOf(state: LiveClient): PlayerState | undefined {
    const { table, viewerSeat } = state;
    return table.players.find((player) => player.seat === viewerSeat);
}

/** The action `intent` sends now: the open decision's answer, on a socket the client can send on; or null. */
function decisionAnswer(state: LiveClient, intent: DecisionIntent): ClientMessage | null {
    const decision = decisionOf(state);
    if (decision === null || !canAnswer(state)) {
        return null;
    }
    return answerDecision(decision, intent, viewerOf(state));
}

/**
 * Whether the decision the seat owes offers `intent`, open or answered: what the dispatcher takes from it until it is
 * answered, and once answered, the controls it was answered from, which never move while the server answers.
 */
export function offersIntent(state: LiveClient, intent: DecisionIntent): boolean {
    const decision = decisionOf(state);
    return (
        decision !== null &&
        canAnswer(state) &&
        offerAnswer(decision, intent, viewerOf(state)) !== null
    );
}

/** Whether the player may turn a play switch on or off now: on a live seat while a round plays. */
function takesSwitch(state: LiveClient): boolean {
    const { session, table, viewerSeat } = state;
    return !hasEnded(session) && viewerSeat !== null && table.phase === "in_round";
}

/**
 * Whether stepping `intent` now would answer the open decision, confirm the round result, reopen the game's last
 * one or turn a play switch: the one test of what the client may play, so the board offers exactly the intents the dispatcher takes.
 */
export function takesIntent(state: LiveClient, intent: PlayIntent): boolean {
    if (intent.type === "confirm_result") {
        return confirmStep(state, canAnswer(state)) !== null;
    }
    if (intent.type === "show_last_result") {
        return reopenResultStep(state) !== null;
    }
    if (intent.type === "toggle_switch") {
        return takesSwitch(state);
    }
    return decisionAnswer(state, intent) !== null;
}

/**
 * Answer the open decision, by the player's press or by the play switch `bySwitch`: send the action it takes and mark
 * it submitted, or change nothing.
 */
export function decisionIntentStep(
    state: LiveClient,
    intent: DecisionIntent,
    bySwitch: PlaySwitch | null,
): ClientStep<LiveClient> {
    const decision = decisionOf(state);
    const message = decisionAnswer(state, intent);
    if (decision === null || message === null) {
        return { effects: [], state };
    }
    const status = { at: state.now, bySwitch, intent, kind: "submitted" } as const;
    return {
        effects: [{ message, type: "send" }],
        state: replaceDecision(state, { ...decision, status }),
    };
}

/**
 * The play switches' standing answer to a decision a message opened on a wait above the highest the game opened before
 * it (`highestBefore`), taken exactly where the player's press would be; nothing for a decision already open, re-sent after
 * a reconnect or reopened by a refusal, which stay the player's.
 */
export function switchStep(
    state: LiveClient,
    highestBefore: number | null,
): ClientStep<LiveClient> {
    const decision = decisionOf(state);
    if (decision?.status.kind !== "open" || !unseenWait(decision.waitId, highestBefore)) {
        return { effects: [], state };
    }
    const answer = switchAnswer(decision, state.switches);
    return answer === null
        ? { effects: [], state }
        : decisionIntentStep(state, answer.intent, answer.bySwitch);
}

/** Turn a play switch on or off, sending nothing: it answers the waits the client sees from then on. */
export function toggleSwitchStep(
    state: LiveClient,
    playSwitch: PlaySwitch,
): ClientStep<LiveClient> | null {
    if (!takesSwitch(state)) {
        return null;
    }
    const switches = { ...state.switches, [playSwitch]: !state.switches[playSwitch] };
    return { effects: [], state: { ...state, switches } };
}
