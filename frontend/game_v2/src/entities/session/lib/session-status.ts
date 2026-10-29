import { type EndReason, type LinkState, type SessionState } from "@/entities/session/model/types";
import { assertNever } from "@/shared/lib";
import { CONNECTION_STATUS, type ConnectionStatus } from "@/shared/protocol";

export interface SessionStatusDisplay {
    readonly label: string;
    readonly tone: ConnectionStatus;
}

const LINK_TONES: Readonly<Record<LinkState, ConnectionStatus>> = {
    connecting: CONNECTION_STATUS.CONNECTING,
    down: CONNECTION_STATUS.DISCONNECTED,
    open: CONNECTION_STATUS.CONNECTED,
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
    const retry = state.retry === null ? "" : `, ${state.retry.kind} retry pending`;
    return { label: `${state.status} (${state.link}${retry})`, tone: LINK_TONES[state.link] };
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
    if (state.status === "reconnecting" || state.link !== "open") {
        return state.lostSeat ? "Reconnecting" : "Connecting";
    }
    return state.status === "joining" ? "Joining the game" : "Connected";
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
