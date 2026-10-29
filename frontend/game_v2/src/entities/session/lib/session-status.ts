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

function describeEnd(reason: EndReason): string {
    switch (reason.kind) {
        case "game_ended": {
            return "game ended";
        }
        case "no_handoff": {
            return "no game session, redirecting to lobby";
        }
        case "left": {
            return "left the game";
        }
        case "closed": {
            return `closed (${reason.code} ${reason.reason}), redirecting to lobby`;
        }
        case "refused": {
            return `refused (${reason.code}), redirecting to lobby`;
        }
        case "retries_exhausted": {
            return `${reason.retry} retries exhausted, redirecting to lobby`;
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
    const retry = state.retry === null ? "" : `, ${state.retry.kind} retry pending`;
    return { label: `${state.status} (${state.link}${retry})`, tone: LINK_TONES[state.link] };
}
