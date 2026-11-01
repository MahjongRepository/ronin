import { assertNever } from "@/shared/lib";

import { hasLostSeat } from "./transition";
import { type EndReason, type SessionState } from "./types";

/**
 * Why a session working for its seat keeps the player waiting: it is finding the player's game, it lost the seat this
 * page held to a drop, or its connection failed since the page opened. A page that only resumes its seat (a reload) on
 * its first try has none.
 */
export type ConnectionTrouble = "finding_game" | "seat_lost" | "unreachable";

/** What keeps the player from their seat while the session works for it; null while it holds the seat or once it ended. */
export function connectionTrouble(state: SessionState): ConnectionTrouble | null {
    switch (state.status) {
        case "ended":
        case "playing": {
            return null;
        }
        case "recovering": {
            return "finding_game";
        }
        case "connecting":
        case "identifying":
        case "awaiting_retry": {
            if (hasLostSeat(state)) {
                return "seat_lost";
            }
            return state.attempts.transport > 0 ? "unreachable" : null;
        }
        default: {
            return assertNever(state);
        }
    }
}

/** Why the session ended, or null while it runs. */
export function endReasonOf(state: SessionState): EndReason | null {
    return state.status === "ended" ? state.reason : null;
}

/** Whether the session ended: it acts on nothing again. */
export function hasEnded(state: SessionState): boolean {
    return endReasonOf(state) !== null;
}

/**
 * Whether leaving now hands the seat to an AI: the session holds it or works for it on a handoff. Finding the game or an
 * end leaves no seat behind.
 */
export function leavingHandsSeatToAi(state: SessionState): boolean {
    switch (state.status) {
        case "ended":
        case "recovering": {
            return false;
        }
        case "connecting":
        case "identifying":
        case "awaiting_retry":
        case "playing": {
            return true;
        }
        default: {
            return assertNever(state);
        }
    }
}
