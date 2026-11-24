import { hasEnded, holdsSeat } from "@/entities/session";
import { DISCARD_LANDING_MS, DRAW_HOLD_MS, type PlayerState } from "@/entities/table";
import { type ClientMessage } from "@/shared/protocol";

import { answerDecision } from "./decision";
import { confirmOpeningStep } from "./opening";
import { decisionOf, replaceDecision } from "./pending";
import { type SwitchAnswer, switchAnswer, unseenWait } from "./play-switches";
import { confirmStep, reopenResultStep } from "./round-confirm";
import {
    type AutomaticAnswer,
    type ClientStep,
    type Decision,
    type DecisionIntent,
    type LiveClient,
    type PlayIntent,
    type PlaySwitch,
} from "./types";

const AUTOMATIC_DRAW_HOLD_MS = 1000;
const AUTO_WIN_PAUSE_MS = 500;
export const AUTO_WIN_RON_HOLD_MS = DISCARD_LANDING_MS + AUTO_WIN_PAUSE_MS;
export const AUTO_WIN_TSUMO_HOLD_MS = DISCARD_LANDING_MS + DRAW_HOLD_MS + AUTO_WIN_PAUSE_MS;

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
 * one, press the opening screen's OK or turn a play switch: the one test of what the client may play, so the board
 * offers exactly the intents the dispatcher takes.
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
    if (intent.type === "confirm_opening") {
        return confirmOpeningStep(state, canAnswer(state)) !== null;
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
        state: replaceDecision(state, { ...decision, status }),
    };
}

/**
 * The answer held before it is sent, or null: Auto win's ron once the discard it takes has landed and its tsumo once
 * the draw has shown, each with a pause after; and the discard of a plain draw after riichi or with Auto discard on,
 * once the drawn tile has stood a second in the hand.
 */
function heldAnswer(
    state: LiveClient,
    decision: Decision,
    answer: SwitchAnswer | null,
): Omit<AutomaticAnswer, "waitId"> | null {
    if (answer?.bySwitch === "auto_win") {
        const hold = decision.kind === "call" ? AUTO_WIN_RON_HOLD_MS : AUTO_WIN_TSUMO_HOLD_MS;
        return { ...answer, due: state.now + hold };
    }
    if (
        decision.kind !== "turn" ||
        decision.opening.kind !== "draw" ||
        decision.offers.length > 0 ||
        !(viewerOf(state)?.isRiichi || answer?.bySwitch === "auto_discard")
    ) {
        return null;
    }
    return {
        bySwitch: answer?.bySwitch ?? null,
        due: state.now + AUTOMATIC_DRAW_HOLD_MS,
        intent: { tileId: decision.opening.drawnTileId, type: "discard" },
    };
}

/**
 * The automatic answer to a decision a message opened on a wait above the highest the game opened before
 * it (`highestBefore`), taken exactly where the player's press would be, held first when `heldAnswer` holds it;
 * nothing for a decision already open, re-sent after a reconnect or reopened by a refusal, which stay the player's.
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
    const held = heldAnswer(state, decision, answer);
    if (held !== null) {
        return {
            effects: [],
            state: { ...state, automaticAnswer: { ...held, waitId: decision.waitId } },
        };
    }
    return answer === null
        ? { effects: [], state }
        : decisionIntentStep(state, answer.intent, answer.bySwitch);
}

/** Whether a held answer is still wanted: a discard while Auto discard is on or the hand in riichi, a win while Auto win is on. */
function stillWanted(state: LiveClient, held: AutomaticAnswer): boolean {
    return held.intent.type === "discard"
        ? state.switches.auto_discard || viewerOf(state)?.isRiichi === true
        : state.switches.auto_win;
}

export function settleAutomaticAnswer(state: LiveClient): LiveClient {
    const held = state.automaticAnswer;
    const decision = decisionOf(state);
    if (held === null) {
        return state;
    }
    if (
        !canAnswer(state) ||
        decision?.waitId !== held.waitId ||
        decision.status.kind === "submitted" ||
        !stillWanted(state, held)
    ) {
        return { ...state, automaticAnswer: null };
    }
    return state;
}

export function sendHeldAnswerStep(state: LiveClient): ClientStep<LiveClient> {
    const settled = settleAutomaticAnswer(state);
    const held = settled.automaticAnswer;
    if (held === null || state.now < held.due) {
        return { effects: [], state: settled };
    }
    return decisionIntentStep({ ...settled, automaticAnswer: null }, held.intent, held.bySwitch);
}

/**
 * The answer a play switch turned on in `state` gives the decision open now, as it would a wait seen from then on:
 * only when that switch gives it, so turning one on never sends what another switch left to the player.
 */
function switchedOnStep(state: LiveClient, playSwitch: PlaySwitch): ClientStep<LiveClient> {
    const decision = decisionOf(state);
    const answer = decision?.status.kind === "open" ? switchAnswer(decision, state.switches) : null;
    return answer?.bySwitch === playSwitch
        ? decisionIntentStep(state, answer.intent, playSwitch)
        : { effects: [], state };
}

/**
 * Change whether Auto win carries into the next round, which the driver keeps in this browser. Turning it on turns
 * Auto win on too, which answers the open decision at once; turning it off leaves Auto win as it is.
 */
export function toggleKeepAutoWinStep(state: LiveClient): ClientStep<LiveClient> {
    const keepAutoWin = !state.keepAutoWin;
    const switches = { ...state.switches, auto_win: keepAutoWin || state.switches.auto_win };
    const saved = { keep: keepAutoWin, type: "save_keep_auto_win" } as const;
    const kept = { ...state, keepAutoWin, switches };
    if (state.switches.auto_win || !switches.auto_win) {
        return { effects: [saved], state: kept };
    }
    const answered = switchedOnStep(kept, "auto_win");
    return { effects: [saved, ...answered.effects], state: answered.state };
}

/**
 * Turn a play switch on or off. Turning one on answers the decision open now as it would the waits the client sees
 * from then on; turning one off sends nothing.
 */
export function toggleSwitchStep(
    state: LiveClient,
    playSwitch: PlaySwitch,
): ClientStep<LiveClient> | null {
    if (!takesSwitch(state)) {
        return null;
    }
    const switches = { ...state.switches, [playSwitch]: !state.switches[playSwitch] };
    const toggled = { ...state, switches };
    return switches[playSwitch]
        ? switchedOnStep(toggled, playSwitch)
        : { effects: [], state: toggled };
}
