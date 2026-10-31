import { type ParsedServerMessage, buildConfirmRoundAction } from "@/shared/protocol";

import { refusalOf } from "./decision";
import { replaceRoundConfirm, roundConfirmOf } from "./pending";
import { type ClientStep, type LiveClient, type RoundConfirm } from "./types";

const MS_PER_SECOND = 1000;
const CONFIRMED: RoundConfirm = { kind: "confirmed" };

/**
 * When the server's round advance timer likely runs out, in logical time: the whole timeout the server names for the
 * round advance, less the time it has run already.
 */
function roundAdvanceDeadline(now: number, seconds: number, elapsedSeconds: number): number {
    return now + Math.max(0, seconds - elapsedSeconds) * MS_PER_SECOND;
}

/**
 * The round confirm a reconnect's snapshot names: none outside a round advance; owed, with a deadline only when the
 * snapshot says how long its timer has run, never a fresh full timeout; or confirmed already. A confirm the seat sent
 * for the wait the snapshot still names stays sent: a late second snapshot after a resync can follow the confirm.
 */
function reconnectRoundConfirm(
    state: LiveClient,
    snapshot: Extract<ParsedServerMessage, { type: "game_reconnected" }>,
): RoundConfirm | null {
    const { advanceTimer, confirmationOwed, waitId } = snapshot;
    const roundConfirm = roundConfirmOf(state);
    if (state.table.roundEndResult === null) {
        return null;
    }
    if (!confirmationOwed) {
        return CONFIRMED;
    }
    if (roundConfirm?.kind === "sent" && roundConfirm.waitId === waitId) {
        return roundConfirm;
    }
    const deadline =
        advanceTimer === null
            ? null
            : roundAdvanceDeadline(state.now, advanceTimer.seconds, advanceTimer.elapsedSeconds);
    return { deadline, kind: "owed", waitId };
}

/**
 * The round confirm a message opens, from the table it left, in place of whatever the seat owed: a round end's wait, a
 * reconnect's snapshot of a round advance. Null for a round end with no wait, a snapshot of no round advance and the
 * game's end, which owe none; undefined for any other message.
 */
export function openedRoundConfirm(
    state: LiveClient,
    message: ParsedServerMessage,
): RoundConfirm | null | undefined {
    switch (message.type) {
        case "round_end": {
            const { roundAdvance } = message;
            if (roundAdvance === null) {
                return null;
            }
            const deadline = roundAdvanceDeadline(state.now, roundAdvance.seconds, 0);
            return { deadline, kind: "owed", waitId: roundAdvance.waitId };
        }
        case "game_reconnected": {
            return reconnectRoundConfirm(state, message);
        }
        case "game_end": {
            return null;
        }
        default: {
            return undefined;
        }
    }
}

/**
 * The round confirm after a message that opens none: closed by the next deal alone, and a sent one reopened as owed
 * only by a refusal that names its wait id. A late refusal of an earlier move names that move's wait, and the
 * confirm's own stale reply follows the deal that closed it already.
 */
export function followRoundConfirm(
    confirm: RoundConfirm,
    message: ParsedServerMessage,
): RoundConfirm | null {
    if (message.type === "round_started") {
        return null;
    }
    if (confirm.kind === "sent" && refusalOf(message)?.waitId === confirm.waitId) {
        return { deadline: confirm.deadline, kind: "owed", waitId: confirm.waitId };
    }
    return confirm;
}

/**
 * Whether the game's last result shows over the standings after a message: the game's end shows it when it follows a
 * round end, and nothing else changes it.
 */
export function showsLastResultAfter(state: LiveClient, message: ParsedServerMessage): boolean {
    return message.type === "game_end"
        ? state.table.roundEndResult !== null
        : state.showsLastResult;
}

/**
 * Confirm the round result: send the owed confirm by its wait id once, on a socket the client can send on
 * (`sendable`), and wait for the others; or dismiss the game's last result for the standings, sending nothing. Null
 * when there is nothing to confirm.
 */
export function confirmStep(state: LiveClient, sendable: boolean): ClientStep<LiveClient> | null {
    if (state.showsLastResult) {
        return { effects: [], state: { ...state, showsLastResult: false } };
    }
    const roundConfirm = roundConfirmOf(state);
    if (roundConfirm?.kind !== "owed" || !sendable) {
        return null;
    }
    const { deadline, waitId } = roundConfirm;
    return {
        effects: [{ message: buildConfirmRoundAction(waitId), type: "send" }],
        state: replaceRoundConfirm(state, { deadline, kind: "sent", waitId }),
    };
}

/**
 * Reopen the game's last result over the standings it was dismissed for, sending nothing. Null unless the game ended on
 * a result the standings show.
 */
export function reopenResultStep(state: LiveClient): ClientStep<LiveClient> | null {
    const { showsLastResult, table } = state;
    if (table.phase !== "game_ended" || table.roundEndResult === null || showsLastResult) {
        return null;
    }
    return { effects: [], state: { ...state, showsLastResult: true } };
}
