import { CLOSE_CODE, SESSION_ERROR_CODE } from "@/shared/protocol";

import { type RetryKind } from "./types";

/**
 * Closes after which the client must not reconnect (`docs/architecture.md`, Game client contract): another
 * socket of the seat took it over, or the server kicked the seat. Every other close is retried, a 1000
 * `game_ended` included, so a client that missed the game end is refused into the lobby.
 */
const TERMINAL_CLOSE_CODES: ReadonlySet<number> = new Set([
    CLOSE_CODE.INVALID_GAME_ACTION,
    CLOSE_CODE.REPLACED_BY_NEW_CONNECTION,
]);

/** Session errors that mean this ticket will never hold the seat again: the player goes back to the lobby. */
const REFUSAL_CODES: ReadonlySet<string> = new Set([
    SESSION_ERROR_CODE.INTERNAL_ERROR,
    SESSION_ERROR_CODE.INVALID_TICKET,
    SESSION_ERROR_CODE.JOIN_GAME_NOT_FOUND,
    SESSION_ERROR_CODE.JOIN_GAME_NO_SESSION,
    SESSION_ERROR_CODE.NOT_IN_GAME,
    SESSION_ERROR_CODE.RECONNECT_ALREADY_ACTIVE,
    SESSION_ERROR_CODE.RECONNECT_GAME_MISMATCH,
    SESSION_ERROR_CODE.RECONNECT_NO_SESSION,
]);

/**
 * Session errors that refuse only this one identity message, so the session sends it again after a session retry.
 * Of the errors that are not refusals, only the rate limit can answer a JOIN_GAME or RECONNECT the client sends
 * well formed, once per socket: `already_in_game` needs a second identity message on a bound socket and
 * `game_not_started` a game action (`backend/game/session/manager.py`).
 */
const RESENDABLE_CODES: ReadonlySet<string> = new Set([SESSION_ERROR_CODE.RATE_LIMITED]);

interface RetryBudget {
    readonly maxAttempts: number;
    readonly maxDelayMs: number;
}

const RETRY_BUDGETS: Readonly<Record<RetryKind, RetryBudget>> = {
    session: { maxAttempts: 15, maxDelayMs: 15_000 },
    transport: { maxAttempts: 10, maxDelayMs: 30_000 },
};

const FIRST_RETRY_DELAY_MS = 1000;

export function isTerminalClose(code: number): boolean {
    return TERMINAL_CLOSE_CODES.has(code);
}

export function isRefusal(code: string): boolean {
    return REFUSAL_CODES.has(code);
}

export function isResendable(code: string): boolean {
    return RESENDABLE_CODES.has(code);
}

/** The delay before a retry's numbered attempt (1-based), or null once its budget is spent. */
export function retryDelayMs(kind: RetryKind, attempt: number): number | null {
    const budget = RETRY_BUDGETS[kind];
    if (attempt > budget.maxAttempts) {
        return null;
    }
    return Math.min(FIRST_RETRY_DELAY_MS * 2 ** (attempt - 1), budget.maxDelayMs);
}
