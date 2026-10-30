import { type EndReason, type SessionState } from "@/entities/session";
import { assertNever } from "@/shared/lib";
import { CLOSE_CODE, SESSION_ERROR_CODE } from "@/shared/protocol";

import { type PlayCommand, type PlayUi } from "./play-ui";
import { type LiveClient } from "./types";

/**
 * The way back to the lobby: its command, which asks first while leaving would hand a held seat to an AI and goes
 * straight to the lobby once the session ended; and whether the player is being asked.
 */
export interface LeaveControls {
    readonly command: PlayCommand;
    readonly confirming: boolean;
}

/** An end that stopped the session on the page: why, in a player's terms, and whether reloading may help. */
export interface FailureDisplay {
    readonly title: string;
    readonly detail: string;
    readonly reload: boolean;
}

const LEAVE: PlayCommand = { intent: { type: "leave" }, kind: "intent" };
const ASK_LEAVE: PlayCommand = { kind: "ask_leave" };

/** Whether leaving now hands a seat the session holds or works for to an AI. */
function leavingNeedsConfirm(session: SessionState): boolean {
    return session.status !== "ended" && session.status !== "recovering";
}

/** The way back to the lobby, asking first while leaving would hand the seat to an AI. */
export function leaveControls(state: LiveClient, ui: PlayUi): LeaveControls {
    if (!leavingNeedsConfirm(state.session)) {
        return { command: LEAVE, confirming: false };
    }
    return { command: ASK_LEAVE, confirming: ui.confirmingLeave };
}

const DISCONNECTED_FAILURE: FailureDisplay = {
    detail: "The connection to the game ended.",
    reload: false,
    title: "Disconnected",
};

function closedFailure(code: number): FailureDisplay {
    if (code === CLOSE_CODE.REPLACED_BY_NEW_CONNECTION) {
        return {
            detail: "Your seat is now played from another tab or device.",
            reload: false,
            title: "Opened elsewhere",
        };
    }
    if (code === CLOSE_CODE.INVALID_GAME_ACTION) {
        return {
            detail: "The server ended your session after a move it could not accept.",
            reload: false,
            title: "Removed from the game",
        };
    }
    return DISCONNECTED_FAILURE;
}

/**
 * Refusals of the identity message on this connection rather than of the ticket: the server would not seat it there, or
 * could not read what it sent.
 */
const SEAT_REFUSED_ON_CONNECTION: ReadonlySet<string> = new Set([
    SESSION_ERROR_CODE.ALREADY_IN_GAME,
    SESSION_ERROR_CODE.INVALID_MESSAGE,
    SESSION_ERROR_CODE.RECONNECT_ALREADY_ACTIVE,
]);

/**
 * A refusal of the ticket: the handoff is forgotten already, so a reload asks the lobby for the player's game afresh
 * and lands wherever they play now.
 */
function refusedFailure(code: string): FailureDisplay {
    if (SEAT_REFUSED_ON_CONNECTION.has(code)) {
        return {
            detail: "The game server would not resume your seat on this connection.",
            reload: true,
            title: "Session error",
        };
    }
    if (code === SESSION_ERROR_CODE.INTERNAL_ERROR) {
        return {
            detail: "The game server could not go on with your session.",
            reload: true,
            title: "Server error",
        };
    }
    return {
        detail: "This game has ended, or this page no longer holds your seat in it.",
        reload: true,
        title: "Game unavailable",
    };
}

function exhaustedFailure(gameStarted: boolean): FailureDisplay {
    if (!gameStarted) {
        return {
            detail: "Could not connect to the game server.",
            reload: true,
            title: "Cannot reach the game",
        };
    }
    return {
        detail: "Could not reconnect to the game. An AI plays your seat meanwhile.",
        reload: true,
        title: "Connection lost",
    };
}

/** What an end that stays on the page tells the player; null for one that leaves it or shows the standings. */
function endFailure(reason: EndReason): FailureDisplay | null {
    switch (reason.kind) {
        case "closed": {
            return closedFailure(reason.code);
        }
        case "refused": {
            return refusedFailure(reason.code);
        }
        case "retries_exhausted": {
            return exhaustedFailure(reason.gameStarted);
        }
        case "recovery_failed": {
            return {
                detail: "The lobby did not say which game you play. Try again in a moment.",
                reload: true,
                title: "Can't reach the lobby",
            };
        }
        case "failed": {
            return {
                detail: "The game page ran into an error.",
                reload: true,
                title: "Something went wrong",
            };
        }
        case "game_ended":
        case "no_handoff":
        case "left":
        case "moved": {
            return null;
        }
        default: {
            return assertNever(reason);
        }
    }
}

/** What an end that stopped the session on the page tells the player; null while it runs or once it left. */
export function failureDisplay(session: SessionState): FailureDisplay | null {
    return session.status === "ended" ? endFailure(session.reason) : null;
}
