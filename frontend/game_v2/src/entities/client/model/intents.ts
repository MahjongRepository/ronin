import { hasEnded, holdsSeat } from "@/entities/session";
import { type PlayerState } from "@/entities/table";
import { type ClientMessage } from "@/shared/protocol";

import { declareIntent } from "./calls";
import { answerDecision } from "./decision";
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

const RIICHI_DRAW_HOLD_MS = 1000;

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
 * Answer the open decision, by the player's press, a riichi discard or the play switch `bySwitch`: send the action it takes and mark
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
        state: replaceDecision(
            { ...state, calls: declareIntent(state, intent, bySwitch) },
            { ...decision, status },
        ),
    };
}

/**
 * The automatic answer to a decision a message opened on a wait above the highest the game opened before
 * it (`highestBefore`), taken exactly where the player's press would be; nothing for a decision already open, re-sent after
 * a reconnect or reopened by a refusal, which stay the player's.
 */
export function automaticStep(
    state: LiveClient,
    highestBefore: number | null,
): ClientStep<LiveClient> {
    const decision = decisionOf(state);
    if (decision?.status.kind !== "open" || !unseenWait(decision.waitId, highestBefore)) {
        return { effects: [], state };
    }
    const answer = switchAnswer(decision, state.switches);
    if (
        decision.kind === "turn" &&
        decision.opening.kind === "draw" &&
        decision.offers.length === 0 &&
        viewerOf(state)?.isRiichi
    ) {
        return {
            effects: [],
            state: {
                ...state,
                riichiDiscard: {
                    bySwitch: answer?.bySwitch ?? null,
                    due: state.now + RIICHI_DRAW_HOLD_MS,
                    tileId: decision.opening.drawnTileId,
                    waitId: decision.waitId,
                },
            },
        };
    }
    return answer === null
        ? { effects: [], state }
        : decisionIntentStep(state, answer.intent, answer.bySwitch);
}

export function settleRiichiDiscard(state: LiveClient): LiveClient {
    const scheduled = state.riichiDiscard;
    const decision = decisionOf(state);
    if (scheduled === null) {
        return state;
    }
    if (
        !canAnswer(state) ||
        decision?.waitId !== scheduled.waitId ||
        decision.status.kind === "submitted"
    ) {
        return { ...state, riichiDiscard: null };
    }
    return state;
}

export function discardRiichiDrawStep(state: LiveClient): ClientStep<LiveClient> {
    const settled = settleRiichiDiscard(state);
    const scheduled = settled.riichiDiscard;
    if (scheduled === null || state.now < scheduled.due) {
        return { effects: [], state: settled };
    }
    return decisionIntentStep(
        { ...settled, riichiDiscard: null },
        { tileId: scheduled.tileId, type: "discard" },
        scheduled.bySwitch,
    );
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
