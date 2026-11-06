import { hasLostSeat } from "@/entities/session/model/transition";
import {
    type ActiveSession,
    type EndReason,
    type Identity,
    type SessionState,
    type TerminalCloseCode,
} from "@/entities/session/model/types";
import { type MessageKey, t } from "@/shared/i18n";
import { assertNever } from "@/shared/lib";
import { CLOSE_CODE, CONNECTION_STATUS, type ConnectionStatus } from "@/shared/protocol";

export interface SessionStatusDisplay {
    readonly label: string;
    readonly tone: ConnectionStatus;
    /**
     * The short word the page's corner shows beside its dot: none while connected or once the player left, what
     * happened once the session ended (ended, replaced), else the socket's state.
     */
    readonly word: string;
}

/** A running session's word, by its socket: none while it is open. */
const ACTIVE_WORDS: Readonly<Record<ConnectionStatus, MessageKey | null>> = {
    [CONNECTION_STATUS.CONNECTED]: null,
    [CONNECTION_STATUS.CONNECTING]: "game.status.connecting",
    [CONNECTION_STATUS.DISCONNECTED]: "game.status.word.offline",
    [CONNECTION_STATUS.ERROR]: "game.status.word.error",
};

/** A terminal close's word: the seat taken by another socket, or removed by the server. */
const CLOSED_WORDS: Readonly<Record<TerminalCloseCode, MessageKey>> = {
    [CLOSE_CODE.INVALID_GAME_ACTION]: "game.status.word.removed",
    [CLOSE_CODE.REPLACED_BY_NEW_CONNECTION]: "game.status.word.replaced",
};

/** What an ended session's word says happened; none for an end that leaves the page. */
function endWord(reason: EndReason): MessageKey | null {
    switch (reason.kind) {
        case "game_ended": {
            return "game.status.word.ended";
        }
        case "closed": {
            return CLOSED_WORDS[reason.code];
        }
        case "retries_exhausted": {
            return "game.status.word.offline";
        }
        case "refused":
        case "failed":
        case "recovery_failed": {
            return "game.status.word.error";
        }
        case "left":
        case "moved":
        case "no_handoff": {
            return null;
        }
        default: {
            return assertNever(reason);
        }
    }
}

/**
 * An ended session's tone: the quiet ended tone for an end that is no failure (the game's, the player's own leaving,
 * the seat taken by another tab), the error's for the rest.
 */
function endTone(reason: EndReason): ConnectionStatus {
    const quiet =
        reason.kind === "game_ended" ||
        reason.kind === "left" ||
        (reason.kind === "closed" && reason.code === CLOSE_CODE.REPLACED_BY_NEW_CONNECTION);
    return quiet ? CONNECTION_STATUS.DISCONNECTED : CONNECTION_STATUS.ERROR;
}

function wordText(key: MessageKey | null): string {
    return key === null ? "" : t(key);
}

/** Each active state's tone, from its socket: opening, open, or down until a transport retry. */
const ACTIVE_TONES: Readonly<Record<ActiveSession["status"], ConnectionStatus>> = {
    awaiting_retry: CONNECTION_STATUS.DISCONNECTED,
    connecting: CONNECTION_STATUS.CONNECTING,
    identifying: CONNECTION_STATUS.CONNECTED,
    playing: CONNECTION_STATUS.CONNECTED,
};

/** How asking the lobby for the player's game ended the session. */
function describeRecoveryEnd(
    reason: Extract<EndReason, { kind: "no_handoff" | "recovery_failed" | "moved" }>,
): string {
    if (reason.kind === "moved") {
        return `playing ${reason.gameId}, redirecting there`;
    }
    return reason.kind === "no_handoff"
        ? "no game session, redirecting to lobby"
        : `game session lookup failed: ${reason.detail}`;
}

function describeEnd(reason: EndReason): string {
    switch (reason.kind) {
        case "game_ended": {
            return "game ended";
        }
        case "no_handoff":
        case "recovery_failed":
        case "moved": {
            return describeRecoveryEnd(reason);
        }
        case "left": {
            return "left the game";
        }
        case "closed": {
            return `closed (${reason.code} ${reason.reason})`;
        }
        case "refused": {
            return `refused (${reason.code})`;
        }
        case "retries_exhausted": {
            return `${reason.retry} retries exhausted`;
        }
        case "failed": {
            return `failed: ${reason.detail}`;
        }
        default: {
            return assertNever(reason);
        }
    }
}

/** The status line the log view shows for a session. */
export function describeSessionStatus(state: SessionState): SessionStatusDisplay {
    if (state.status === "ended") {
        return {
            label: describeEnd(state.reason),
            tone: endTone(state.reason),
            word: wordText(endWord(state.reason)),
        };
    }
    if (state.status === "recovering") {
        const tone = CONNECTION_STATUS.CONNECTING;
        return { label: "recovering the handoff", tone, word: wordText(ACTIVE_WORDS[tone]) };
    }
    const tone = ACTIVE_TONES[state.status];
    return { label: describeActive(state), tone, word: wordText(ACTIVE_WORDS[tone]) };
}

function describeIdentity(identity: Identity): string {
    if (identity.kind === "join") {
        return "join";
    }
    return identity.lostSeat ? "reconnect, seat lost" : "reconnect";
}

function describeActive(state: ActiveSession): string {
    switch (state.status) {
        case "playing": {
            return "playing";
        }
        case "connecting": {
            return `connecting (${describeIdentity(state.identity)})`;
        }
        case "identifying": {
            const retry = state.sessionRetryAt === null ? "" : ", session retry pending";
            return `identifying (${describeIdentity(state.identity)}${retry})`;
        }
        case "awaiting_retry": {
            return `awaiting transport retry (${describeIdentity(state.identity)})`;
        }
        default: {
            return assertNever(state);
        }
    }
}

/** A terminal close in the player's words. */
const CLOSED_LABELS: Readonly<Record<TerminalCloseCode, MessageKey>> = {
    [CLOSE_CODE.INVALID_GAME_ACTION]: "game.status.removed",
    [CLOSE_CODE.REPLACED_BY_NEW_CONNECTION]: "game.status.opened_in_another_tab",
};

function describeEndForPlayer(reason: EndReason): MessageKey {
    switch (reason.kind) {
        case "game_ended": {
            return "game.status.game_over";
        }
        case "left": {
            return "game.status.left";
        }
        case "failed": {
            return "game.status.failed";
        }
        case "moved": {
            return "game.status.opening_game";
        }
        case "no_handoff": {
            return "game.status.no_game";
        }
        case "recovery_failed": {
            return "game.status.lobby_unreachable";
        }
        case "closed": {
            return CLOSED_LABELS[reason.code];
        }
        case "refused":
        case "retries_exhausted": {
            return "game.status.disconnected";
        }
        default: {
            return assertNever(reason);
        }
    }
}

function describeActiveForPlayer(state: Exclude<SessionState, { status: "ended" }>): MessageKey {
    if (state.status === "recovering") {
        return "game.status.finding_game";
    }
    if (state.status === "playing") {
        return state.gameStarted ? "game.status.connected" : "game.status.waiting_start";
    }
    if (state.status === "identifying" && state.identity.kind === "join") {
        return "game.status.joining";
    }
    return hasLostSeat(state) ? "game.status.reconnecting" : "game.status.connecting";
}

/** The status a player reads for a session: what it means for them, never the machine's internal states. */
export function describePlayerSessionStatus(state: SessionState): SessionStatusDisplay {
    const { tone, word } = describeSessionStatus(state);
    const label =
        state.status === "ended"
            ? describeEndForPlayer(state.reason)
            : describeActiveForPlayer(state);
    return { label: t(label), tone, word };
}
