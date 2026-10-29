import { assertNever } from "@/shared/lib";
import {
    type ClientMessage,
    type ParsedServerMessage,
    SESSION_ERROR_CODE,
    buildJoinGameMessage,
    buildReconnectMessage,
} from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";

import { isRefusal, isResendable, isTerminalClose, retryDelayMs } from "./policy";
import {
    type ActiveSession,
    type EndReason,
    type EndedSession,
    type RetryKind,
    type SessionEffect,
    type SessionInput,
    type SessionState,
    type SessionStep,
} from "./types";

const NO_ATTEMPTS = { session: 0, transport: 0 } as const;

function unchanged(state: SessionState): SessionStep {
    return { effects: [], state };
}

function identityMessage(session: ActiveSession): ClientMessage {
    const { gameTicket } = session.handoff;
    return session.status === "joining"
        ? buildJoinGameMessage(gameTicket)
        : buildReconnectMessage(gameTicket);
}

function leavesForLobby(reason: EndReason): boolean {
    switch (reason.kind) {
        case "game_ended":
        case "failed": {
            return false;
        }
        case "no_handoff":
        case "left":
        case "closed":
        case "refused":
        case "retries_exhausted": {
            return true;
        }
        default: {
            return assertNever(reason);
        }
    }
}

function lobbyEffects(gameId: string): SessionEffect[] {
    return [{ gameId, type: "clear_handoff" }, { type: "redirect_to_lobby" }];
}

/**
 * End the session, dropping its retry: close its socket, then, unless the end stays on the page, forget the
 * handoff and leave for the lobby. A game that ended keeps its socket for the server to close.
 */
function endSession(session: ActiveSession, reason: EndReason): SessionStep {
    const effects: SessionEffect[] = [];
    if (session.link !== "down" && reason.kind !== "game_ended") {
        effects.push({ type: "close_socket" });
    }
    if (leavesForLobby(reason)) {
        effects.push(...lobbyEffects(session.gameId));
    }
    const state: EndedSession = { gameId: session.gameId, reason, status: "ended" };
    return { effects, state };
}

/** Leave for the lobby from an end that stayed on the page; any other end is already leaving. */
function leaveEnded(ended: EndedSession): SessionStep {
    if (leavesForLobby(ended.reason)) {
        return unchanged(ended);
    }
    return {
        effects: [{ type: "close_socket" }, ...lobbyEffects(ended.gameId)],
        state: { ...ended, reason: { kind: "left" } },
    };
}

function scheduleRetry(session: ActiveSession, kind: RetryKind, at: number): SessionStep {
    const attempt = session.attempts[kind] + 1;
    const delayMs = retryDelayMs(kind, attempt);
    if (delayMs === null) {
        return endSession(session, { kind: "retries_exhausted", retry: kind });
    }
    return {
        effects: [],
        state: {
            ...session,
            attempts: { ...session.attempts, [kind]: attempt },
            retry: { dueAt: at + delayMs, kind },
        },
    };
}

function admit(session: ActiveSession): SessionStep {
    return {
        effects: [],
        state: { ...session, attempts: NO_ATTEMPTS, retry: null, status: "playing" },
    };
}

function onTransportOpened(session: ActiveSession): SessionStep {
    if (session.link !== "connecting") {
        return unchanged(session);
    }
    return {
        effects: [{ message: identityMessage(session), type: "send" }],
        state: { ...session, link: "open" },
    };
}

/** A drop replaces any session retry with a transport retry: the reopened socket sends RECONNECT itself. */
function onTransportClosed(
    session: ActiveSession,
    { at, code, reason }: Extract<SessionInput, { kind: "transport_closed" }>,
): SessionStep {
    if (session.link === "down") {
        return unchanged(session);
    }
    const dropped: ActiveSession = {
        ...session,
        link: "down",
        retry: null,
        status: session.status === "playing" ? "reconnecting" : session.status,
    };
    if (isTerminalClose(code)) {
        return endSession(dropped, { code, kind: "closed", reason });
    }
    return scheduleRetry(dropped, "transport", at);
}

/**
 * Run the retry that came due: reopen the socket after a drop, or resend the identity message on the open one.
 * A session retry only waits on an open socket, since a drop replaces it with a transport retry.
 */
function onTick(session: ActiveSession, at: number): SessionStep {
    const { retry } = session;
    if (retry === null || at < retry.dueAt) {
        return unchanged(session);
    }
    if (session.link === "down") {
        return {
            effects: [{ type: "open_socket", url: session.handoff.wsUrl }],
            state: { ...session, link: "connecting", retry: null },
        };
    }
    const due: ActiveSession = { ...session, retry: null };
    return { effects: [{ message: identityMessage(due), type: "send" }], state: due };
}

/**
 * Answer a session error. `reconnect_retry_later` only answers a RECONNECT, and a resendable error only matters
 * before the seat is held; while playing, neither can refer to the identity message, so both are ignored.
 */
function onSessionError(session: ActiveSession, code: string, at: number): SessionStep {
    if (code === SESSION_ERROR_CODE.JOIN_GAME_ALREADY_STARTED) {
        const resuming: ActiveSession = { ...session, status: "reconnecting" };
        return { effects: [{ message: identityMessage(resuming), type: "send" }], state: resuming };
    }
    if (isRefusal(code)) {
        return endSession(session, { code, kind: "refused" });
    }
    const retriesIdentity =
        (code === SESSION_ERROR_CODE.RECONNECT_RETRY_LATER && session.status === "reconnecting") ||
        (isResendable(code) && session.status !== "playing");
    return retriesIdentity ? scheduleRetry(session, "session", at) : unchanged(session);
}

function onMessage(session: ActiveSession, message: ParsedServerMessage, at: number): SessionStep {
    if (message.type === "session_error") {
        return onSessionError(session, message.code, at);
    }
    if (message.type === "game_reconnected") {
        return admit(session);
    }
    if (message.type === "player_left" || message.type === "player_reconnected") {
        return unchanged(session);
    }
    if (message.type === "game_end") {
        return endSession(session, { kind: "game_ended" });
    }
    return session.status === "joining" ? admit(session) : unchanged(session);
}

/** Begin a session from the lobby's handoff, or end it at once when the tab holds none. */
export function startSession(gameId: string, handoff: GameSessionData | null): SessionStep {
    if (handoff === null) {
        return {
            effects: lobbyEffects(gameId),
            state: { gameId, reason: { kind: "no_handoff" }, status: "ended" },
        };
    }
    return {
        effects: [{ type: "open_socket", url: handoff.wsUrl }],
        state: {
            attempts: NO_ATTEMPTS,
            gameId,
            handoff,
            link: "connecting",
            retry: null,
            status: "joining",
        },
    };
}

/** When the session next needs a tick: its pending retry's due time, or null. */
export function sessionDeadline(state: SessionState): number | null {
    return state.status === "ended" || state.retry === null ? null : state.retry.dueAt;
}

/**
 * End the session because its driver failed while stepping it or running its effects, replacing any end it had
 * reached: the end stays on the page, showing the failure, and the driver closes the socket itself.
 */
export function failSession(state: SessionState, detail: string): SessionState {
    return { gameId: state.gameId, reason: { detail, kind: "failed" }, status: "ended" };
}

/**
 * The session transition: the next state and the effects it asks for, with no IO, timer or clock read inside.
 * A tick before the pending retry's due time, or with none pending, changes nothing, so a stale timer cannot
 * restart anything; an ended session ignores every input but a leave from an end that stayed on the page.
 */
export function stepSession(state: SessionState, input: SessionInput): SessionStep {
    if (state.status === "ended") {
        return input.kind === "leave" ? leaveEnded(state) : unchanged(state);
    }
    switch (input.kind) {
        case "transport_opened": {
            return onTransportOpened(state);
        }
        case "transport_closed": {
            return onTransportClosed(state, input);
        }
        case "message": {
            return onMessage(state, input.message, input.at);
        }
        case "tick": {
            return onTick(state, input.at);
        }
        case "leave": {
            return endSession(state, { kind: "left" });
        }
        default: {
            return assertNever(input);
        }
    }
}
