import {
    type EndReason,
    type SessionState,
    type TerminalCloseCode,
    endReasonOf,
    leavingHandsSeatToAi,
} from "@/entities/session";
import { type MessageKey } from "@/shared/i18n";
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
    readonly title: MessageKey;
    readonly detail: MessageKey;
    readonly reload: boolean;
}

const LEAVE: PlayCommand = { intent: { type: "leave" }, kind: "intent" };
const ASK_LEAVE: PlayCommand = { kind: "ask_leave" };

/** The way back to the lobby, asking first while leaving would hand the seat to an AI. */
export function leaveControls(state: LiveClient, ui: PlayUi): LeaveControls {
    if (!leavingHandsSeatToAi(state.session)) {
        return { command: LEAVE, confirming: false };
    }
    return { command: ASK_LEAVE, confirming: ui.confirmingLeave };
}

/** A close that ended the session: only the terminal codes do (`TerminalCloseCode`), every other close is retried. */
const CLOSED_FAILURES: Readonly<Record<TerminalCloseCode, FailureDisplay>> = {
    [CLOSE_CODE.INVALID_GAME_ACTION]: {
        detail: "game.failure.removed_detail",
        reload: false,
        title: "game.status.removed",
    },
    [CLOSE_CODE.REPLACED_BY_NEW_CONNECTION]: {
        detail: "game.failure.opened_elsewhere_detail",
        reload: false,
        title: "game.failure.opened_elsewhere",
    },
};

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
            detail: "game.failure.session_error_detail",
            reload: true,
            title: "game.failure.session_error",
        };
    }
    if (code === SESSION_ERROR_CODE.INTERNAL_ERROR) {
        return {
            detail: "game.failure.server_error_detail",
            reload: true,
            title: "game.failure.server_error",
        };
    }
    return {
        detail: "game.failure.unavailable_detail",
        reload: true,
        title: "game.failure.unavailable",
    };
}

function exhaustedFailure(gameStarted: boolean): FailureDisplay {
    if (!gameStarted) {
        return {
            detail: "game.failure.unreachable_detail",
            reload: true,
            title: "game.failure.unreachable",
        };
    }
    return {
        detail: "game.failure.connection_lost_detail",
        reload: true,
        title: "game.failure.connection_lost",
    };
}

/** What an end that stays on the page tells the player; null for one that leaves it or shows the game's end. */
function endFailure(reason: EndReason): FailureDisplay | null {
    switch (reason.kind) {
        case "closed": {
            return CLOSED_FAILURES[reason.code];
        }
        case "refused": {
            return refusedFailure(reason.code);
        }
        case "retries_exhausted": {
            return exhaustedFailure(reason.gameStarted);
        }
        case "recovery_failed": {
            return {
                detail: "game.failure.lobby_unreachable_detail",
                reload: true,
                title: "game.status.lobby_unreachable",
            };
        }
        case "failed": {
            return {
                detail: "game.page.broken",
                reload: true,
                title: "game.status.failed",
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
    const reason = endReasonOf(session);
    return reason === null ? null : endFailure(reason);
}
