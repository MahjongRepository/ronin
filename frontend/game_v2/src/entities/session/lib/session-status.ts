import { hasLostSeat } from "@/entities/session/model/transition";
import {
    type ActiveSession,
    type EndReason,
    type Identity,
    type SessionState,
} from "@/entities/session/model/types";
import { assertNever } from "@/shared/lib";
import { CONNECTION_STATUS, type ConnectionStatus } from "@/shared/protocol";

export interface SessionStatusDisplay {
    readonly label: string;
    readonly tone: ConnectionStatus;
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
        const tone =
            state.reason.kind === "game_ended"
                ? CONNECTION_STATUS.DISCONNECTED
                : CONNECTION_STATUS.ERROR;
        return { label: describeEnd(state.reason), tone };
    }
    if (state.status === "recovering") {
        return { label: "recovering the handoff", tone: CONNECTION_STATUS.CONNECTING };
    }
    return { label: describeActive(state), tone: ACTIVE_TONES[state.status] };
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

function describeEndForPlayer(reason: EndReason): string {
    switch (reason.kind) {
        case "game_ended": {
            return "Game over";
        }
        case "left": {
            return "You left the game";
        }
        case "failed": {
            return "Something went wrong";
        }
        case "moved": {
            return "Opening your game";
        }
        case "no_handoff": {
            return "No game, returning to the lobby";
        }
        case "recovery_failed": {
            return "Can't reach the lobby";
        }
        case "closed":
        case "refused":
        case "retries_exhausted": {
            return "Disconnected";
        }
        default: {
            return assertNever(reason);
        }
    }
}

function describeActiveForPlayer(state: Exclude<SessionState, { status: "ended" }>): string {
    if (state.status === "recovering") {
        return "Finding your game";
    }
    if (state.status === "playing") {
        return "Connected";
    }
    if (state.status === "identifying" && state.identity.kind === "join") {
        return "Joining the game";
    }
    return hasLostSeat(state) ? "Reconnecting" : "Connecting";
}

/** The status a player reads for a session: what it means for them, never the machine's internal states. */
export function describePlayerSessionStatus(state: SessionState): SessionStatusDisplay {
    const { tone } = describeSessionStatus(state);
    const label =
        state.status === "ended"
            ? describeEndForPlayer(state.reason)
            : describeActiveForPlayer(state);
    return { label, tone };
}
