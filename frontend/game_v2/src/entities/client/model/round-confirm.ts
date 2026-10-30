import { roundEndPages } from "@/entities/table";
import {
    type ParsedServerMessage,
    SESSION_ERROR_CODE,
    buildConfirmRoundAction,
} from "@/shared/protocol";

import { type ClientStep, type GameClientState, type RoundConfirm } from "./types";

const MS_PER_SECOND = 1000;
const CONFIRMED: RoundConfirm = { kind: "confirmed" };
const FINAL: RoundConfirm = { kind: "final" };

/**
 * When the server's round advance timer for the table's result likely runs out, in logical time: one deadline per
 * round, the round advance timeout times the result's pages (the server's `results_shown`, a double ron's winners),
 * armed at the round end, less the time the timer has run already.
 */
function roundAdvanceDeadline(state: GameClientState, elapsedSeconds: number): number | null {
    const { now, table, timer } = state;
    if (timer === null || table.roundEndResult === null) {
        return null;
    }
    const seconds = timer.roundAdvanceTimeoutSeconds * roundEndPages(table.roundEndResult).length;
    return now + Math.max(0, seconds - elapsedSeconds) * MS_PER_SECOND;
}

/**
 * The round confirm a reconnect's snapshot names: none outside a round advance; owed, with a deadline only when the
 * snapshot says how long its timer has run, never a fresh full timeout; or confirmed already.
 */
function reconnectRoundConfirm(
    state: GameClientState,
    snapshot: Extract<ParsedServerMessage, { type: "game_reconnected" }>,
): RoundConfirm | null {
    const { confirmationOwed, elapsedSeconds, waitId } = snapshot;
    if (state.table.roundEndResult === null) {
        return null;
    }
    if (!confirmationOwed) {
        return CONFIRMED;
    }
    const deadline = elapsedSeconds === null ? null : roundAdvanceDeadline(state, elapsedSeconds);
    return { deadline, kind: "owed", waitId };
}

/**
 * The round confirm a message opens, from the table it left: a round end's wait, a reconnect's snapshot of a round
 * advance, or the game's last result when the game end follows a round end. Null for a round end with no wait;
 * undefined for any other message.
 */
function openedRoundConfirm(
    state: GameClientState,
    message: ParsedServerMessage,
): RoundConfirm | null | undefined {
    switch (message.type) {
        case "round_end": {
            const { waitId } = message;
            const deadline = roundAdvanceDeadline(state, 0);
            return waitId === null ? null : { deadline, kind: "owed", waitId };
        }
        case "game_reconnected": {
            return reconnectRoundConfirm(state, message);
        }
        case "game_end": {
            return state.table.roundEndResult === null ? null : FINAL;
        }
        default: {
            return undefined;
        }
    }
}

/**
 * The round confirm after a message that opens none: closed by the next deal alone, and a sent one reopened as owed
 * by the socket's rate limit alone. A game error never answers it: a late reply to an earlier move names no wait,
 * and the confirm's own stale reply follows the deal that closed it already.
 */
function followRoundConfirm(
    confirm: RoundConfirm,
    message: ParsedServerMessage,
): RoundConfirm | null {
    if (message.type === "round_started" && confirm.kind !== "final") {
        return null;
    }
    const rateLimited =
        message.type === "session_error" && message.code === SESSION_ERROR_CODE.RATE_LIMITED;
    if (confirm.kind === "sent" && rateLimited) {
        return { deadline: confirm.deadline, kind: "owed", waitId: confirm.waitId };
    }
    return confirm;
}

/** The round confirm after a message: the one it opens, else the open one as the message leaves it. */
export function withRoundConfirm(
    state: GameClientState,
    message: ParsedServerMessage,
): GameClientState {
    const opened = openedRoundConfirm(state, message);
    const { roundConfirm } = state;
    if (opened !== undefined) {
        return { ...state, roundConfirm: opened };
    }
    if (roundConfirm === null) {
        return state;
    }
    return { ...state, roundConfirm: followRoundConfirm(roundConfirm, message) };
}

/**
 * Confirm the round result: send the owed confirm by its wait id once, on a socket the client can send on
 * (`sendable`), and wait for the others; or dismiss the game's last result for the standings, sending nothing. Null
 * when there is nothing to confirm.
 */
export function confirmStep(state: GameClientState, sendable: boolean): ClientStep | null {
    const { roundConfirm } = state;
    if (roundConfirm?.kind === "final") {
        return { effects: [], state: { ...state, roundConfirm: null } };
    }
    if (roundConfirm?.kind !== "owed" || !sendable) {
        return null;
    }
    const { deadline, waitId } = roundConfirm;
    return {
        effects: [{ message: buildConfirmRoundAction(waitId), type: "send" }],
        state: { ...state, roundConfirm: { deadline, kind: "sent", waitId } },
    };
}

/**
 * Reopen the game's last result over the standings it was dismissed for, sending nothing. Null unless the game ended on
 * a result the standings show.
 */
export function reopenResultStep(state: GameClientState): ClientStep | null {
    const { roundConfirm, table } = state;
    if (table.phase !== "game_ended" || table.roundEndResult === null || roundConfirm !== null) {
        return null;
    }
    return { effects: [], state: { ...state, roundConfirm: FINAL } };
}
