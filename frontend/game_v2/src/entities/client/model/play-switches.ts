import { type TableState } from "@/entities/table";

import {
    type CallDecision,
    type Decision,
    type DecisionIntent,
    type PlaySwitch,
    type PlaySwitches,
    type TurnDecision,
} from "./types";

/** The play switches in the order the board shows them. */
export const PLAY_SWITCHES: readonly PlaySwitch[] = ["auto_win", "no_calls", "auto_discard"];

export const SWITCHES_OFF: PlaySwitches = {
    auto_discard: false,
    auto_win: false,
    no_calls: false,
};

/** The answer a play switch gives a decision: the intent the player's press would step, and the switch giving it. */
export interface SwitchAnswer {
    readonly intent: DecisionIntent;
    readonly bySwitch: PlaySwitch;
}

/** A call prompt's answer: Auto win takes its ron; No calls passes one that offers a call and no ron. */
function callAnswer(decision: CallDecision, switches: PlaySwitches): SwitchAnswer | null {
    const kinds = new Set(decision.offers.map((offer) => offer.kind));
    if (switches.auto_win && kinds.has("ron")) {
        return { bySwitch: "auto_win", intent: { offer: { kind: "ron" }, type: "choose" } };
    }
    const passes = switches.no_calls && !kinds.has("ron") && kinds.size > 0;
    return passes ? { bySwitch: "no_calls", intent: { type: "pass" } } : null;
}

/**
 * A turn's answer: Auto win takes its tsumo; Auto discard discards the drawn tile when the turn offers nothing else,
 * never on the turn after the seat's own chi or pon, which drew none.
 */
function turnAnswer(decision: TurnDecision, switches: PlaySwitches): SwitchAnswer | null {
    const { drawnTileId, offers } = decision;
    if (switches.auto_win && offers.some((offer) => offer.kind === "tsumo")) {
        return { bySwitch: "auto_win", intent: { offer: { kind: "tsumo" }, type: "choose" } };
    }
    if (!switches.auto_discard || offers.length > 0 || drawnTileId === null) {
        return null;
    }
    return { bySwitch: "auto_discard", intent: { tileId: drawnTileId, type: "discard" } };
}

/**
 * The answer the switches on give a decision, or null to leave it to the player. A win outranks the rest: Auto win
 * takes a turn's tsumo or a prompt's ron. No calls passes a prompt that offers a call (chi, pon, open kan) and no ron,
 * and never touches a turn. Auto discard discards the drawn tile on a turn that offers nothing else (no tsumo, kan,
 * riichi or kyuushu), and never the turn after the seat's own chi or pon.
 */
export function switchAnswer(decision: Decision, switches: PlaySwitches): SwitchAnswer | null {
    return decision.kind === "call"
        ? callAnswer(decision, switches)
        : turnAnswer(decision, switches);
}

/**
 * Whether a reconnect's snapshot leaves the hand the table played before it: the table before it was not in a round
 * (it showed a result, so any snapshot is of that result or a later hand), or the snapshot is of another game or
 * another count of finished rounds (a later hand, or the hand's own result pending, which counts it finished). The
 * switches are an instruction about one hand, so such a snapshot turns them off.
 */
export function snapshotLeftHand(before: TableState, after: TableState): boolean {
    return (
        before.phase !== "in_round" ||
        before.gameId !== after.gameId ||
        before.roundHistory.length !== after.roundHistory.length
    );
}
