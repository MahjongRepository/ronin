import { type HandoffRecovery } from "@/shared/api";
import { assertNever } from "@/shared/lib";
import {
    CLOSE_CODE,
    type ClientMessage,
    type ParsedServerMessage,
    SESSION_ERROR_CODE,
    buildJoinGameMessage,
    buildReconnectMessage,
} from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";

import {
    CONNECT_TIMEOUT_MS,
    isRefusal,
    isResendable,
    isTerminalClose,
    lookupRetryDelayMs,
    retryDelayMs,
} from "./policy";
import {
    type ActiveSession,
    type EndReason,
    type EndedSession,
    type RecoveringSession,
    type RetryKind,
    type SessionEffect,
    type SessionInput,
    type SessionState,
    type SessionStep,
} from "./types";

const NO_ATTEMPTS = { session: 0, transport: 0 } as const;

/** The close a connect timeout is taken as: what a browser reports for a connection that failed. */
const CONNECT_TIMEOUT_CLOSE = { code: CLOSE_CODE.ABNORMAL, reason: "connect_timeout" } as const;

function unchanged(state: SessionState): SessionStep {
    return { effects: [], state };
}

function identityMessage(session: ActiveSession): ClientMessage {
    const { gameTicket } = session.handoff;
    return session.status === "joining"
        ? buildJoinGameMessage(gameTicket)
        : buildReconnectMessage(gameTicket);
}

/** Where an end takes the player: it stays on the page to say why, or leaves for the lobby or another game. */
type EndPlace = "page" | "lobby" | "elsewhere";

function endPlace(reason: EndReason): EndPlace {
    switch (reason.kind) {
        case "game_ended":
        case "failed":
        case "recovery_failed":
        case "closed":
        case "refused":
        case "retries_exhausted": {
            return "page";
        }
        case "no_handoff":
        case "left": {
            return "lobby";
        }
        case "moved": {
            return "elsewhere";
        }
        default: {
            return assertNever(reason);
        }
    }
}

/** Whether an end means the handoff will never hold the seat again, so the tab forgets it at once. */
function forgetsHandoff(reason: EndReason): boolean {
    switch (reason.kind) {
        case "closed":
        case "refused":
        case "retries_exhausted":
        case "no_handoff":
        case "game_ended":
        case "left": {
            return true;
        }
        case "failed":
        case "recovery_failed":
        case "moved": {
            return false;
        }
        default: {
            return assertNever(reason);
        }
    }
}

function endEffects(gameId: string, reason: EndReason): SessionEffect[] {
    const effects: SessionEffect[] = [];
    if (forgetsHandoff(reason)) {
        effects.push({ gameId, type: "clear_handoff" });
    }
    if (endPlace(reason) === "lobby") {
        effects.push({ type: "redirect_to_lobby" });
    }
    return effects;
}

/**
 * End the session, dropping its retry: close its socket, forget the handoff when it will never hold the seat again,
 * and leave for the lobby when the end does not stay on the page to say why. A game that ended keeps its socket for
 * the server to close.
 */
function endSession(session: ActiveSession, reason: EndReason): SessionStep {
    const effects: SessionEffect[] = [];
    if (session.link !== "down" && reason.kind !== "game_ended") {
        effects.push({ type: "close_socket" });
    }
    effects.push(...endEffects(session.gameId, reason));
    const state: EndedSession = { gameId: session.gameId, reason, status: "ended" };
    return { effects, state };
}

/** Leave for the lobby from an end that stayed on the page; any other end is already leaving. */
function leaveEnded(ended: EndedSession): SessionStep {
    if (endPlace(ended.reason) !== "page") {
        return unchanged(ended);
    }
    const forget: SessionEffect[] = forgetsHandoff(ended.reason)
        ? []
        : [{ gameId: ended.gameId, type: "clear_handoff" }];
    return {
        effects: [{ type: "close_socket" }, ...forget, { type: "redirect_to_lobby" }],
        state: { ...ended, reason: { kind: "left" } },
    };
}

function scheduleRetry(session: ActiveSession, kind: RetryKind, at: number): SessionStep {
    const attempt = session.attempts[kind] + 1;
    const delayMs = retryDelayMs(kind, attempt);
    if (delayMs === null) {
        const gameStarted = session.status !== "joining";
        return endSession(session, { gameStarted, kind: "retries_exhausted", retry: kind });
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

/** Open a socket for the session, which counts as a failed connection unless it opens by its connect deadline. */
function openSocket(session: ActiveSession, at: number): SessionStep {
    return {
        effects: [{ type: "open_socket", url: session.handoff.wsUrl }],
        state: {
            ...session,
            connectDeadline: at + CONNECT_TIMEOUT_MS,
            link: "connecting",
            retry: null,
        },
    };
}

function admit(session: ActiveSession): SessionStep {
    return {
        effects: [],
        state: {
            ...session,
            attempts: NO_ATTEMPTS,
            lostSeat: false,
            retry: null,
            status: "playing",
        },
    };
}

function onTransportOpened(session: ActiveSession): SessionStep {
    if (session.link !== "connecting") {
        return unchanged(session);
    }
    return {
        effects: [{ message: identityMessage(session), type: "send" }],
        state: { ...session, connectDeadline: null, link: "open" },
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
        connectDeadline: null,
        link: "down",
        lostSeat: session.lostSeat || session.status === "playing",
        retry: null,
        status: session.status === "playing" ? "reconnecting" : session.status,
    };
    if (isTerminalClose(code)) {
        return endSession(dropped, { code, kind: "closed", reason });
    }
    return scheduleRetry(dropped, "transport", at);
}

/** A socket that has not opened by its connect deadline: closed, and taken as a failed connection to retry. */
function onConnectTimeout(session: ActiveSession, at: number): SessionStep {
    const step = onTransportClosed(session, {
        at,
        code: CONNECT_TIMEOUT_CLOSE.code,
        kind: "transport_closed",
        reason: CONNECT_TIMEOUT_CLOSE.reason,
    });
    return { effects: [{ type: "close_socket" }, ...step.effects], state: step.state };
}

/**
 * Give up on a socket that never opened, or run the retry that came due: reopen the socket after a drop, or resend
 * the identity message on the open one. A session retry only waits on an open socket, since a drop replaces it with
 * a transport retry.
 */
function onTick(session: ActiveSession, at: number): SessionStep {
    const { connectDeadline, retry } = session;
    if (connectDeadline !== null && at >= connectDeadline) {
        return onConnectTimeout(session, at);
    }
    if (retry === null || at < retry.dueAt) {
        return unchanged(session);
    }
    if (session.link === "down") {
        return openSocket(session, at);
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
    if (message.type === "ai_replacement" || message.type === "human_return") {
        return unchanged(session);
    }
    if (message.type === "game_end") {
        return endSession(session, { kind: "game_ended" });
    }
    return session.status === "joining" ? admit(session) : unchanged(session);
}

function joinWith(gameId: string, handoff: GameSessionData, at: number): SessionStep {
    const joining: ActiveSession = {
        attempts: NO_ATTEMPTS,
        connectDeadline: null,
        gameId,
        handoff,
        link: "down",
        lostSeat: false,
        retry: null,
        status: "joining",
    };
    return openSocket(joining, at);
}

/**
 * Take the lobby's answer for the player's game: join this page's game with its handoff, kept for a reload; keep
 * another game's handoff and go to that game's page; leave for the lobby when the player plays none; or, when the
 * lookup failed, ask again after a wait, and once those retries are spent stay on the page for the player to reload.
 */
function onRecovered(
    session: RecoveringSession,
    recovery: HandoffRecovery,
    at: number,
): SessionStep {
    switch (recovery.kind) {
        case "found": {
            return onFound(session, recovery, at);
        }
        case "missing": {
            return endRecovery(session, { kind: "no_handoff" });
        }
        case "failed": {
            return onLookupFailed(session, recovery.detail, at);
        }
        default: {
            return assertNever(recovery);
        }
    }
}

function onFound(
    { gameId }: RecoveringSession,
    found: Extract<HandoffRecovery, { kind: "found" }>,
    at: number,
): SessionStep {
    const store: SessionEffect = {
        gameId: found.gameId,
        handoff: found.handoff,
        type: "store_handoff",
    };
    if (found.gameId === gameId) {
        const step = joinWith(gameId, found.handoff, at);
        return { effects: [store, ...step.effects], state: step.state };
    }
    const redirect: SessionEffect = {
        gameClientUrl: found.gameClientUrl,
        gameId: found.gameId,
        type: "redirect_to_game",
    };
    return {
        effects: [store, redirect],
        state: { gameId, reason: { gameId: found.gameId, kind: "moved" }, status: "ended" },
    };
}

function onLookupFailed(session: RecoveringSession, detail: string, at: number): SessionStep {
    const failedLookups = session.failedLookups + 1;
    const delayMs = lookupRetryDelayMs(failedLookups);
    if (delayMs === null) {
        return endRecovery(session, { detail, kind: "recovery_failed" });
    }
    return unchanged({ ...session, failedLookups, retryAt: at + delayMs });
}

/** Ask the lobby again once a failed lookup's wait is over. */
function onRecoveringTick(session: RecoveringSession, at: number): SessionStep {
    if (session.retryAt === null || at < session.retryAt) {
        return unchanged(session);
    }
    return { effects: [{ type: "recover_handoff" }], state: { ...session, retryAt: null } };
}

function endRecovery(session: RecoveringSession, reason: EndReason): SessionStep {
    return {
        effects: endEffects(session.gameId, reason),
        state: { gameId: session.gameId, reason, status: "ended" },
    };
}

/**
 * A recovering session takes only the lobby's answer, the tick of a lookup's retry, and a leave, which goes to the
 * lobby at once.
 */
function stepRecovering(session: RecoveringSession, input: SessionInput): SessionStep {
    switch (input.kind) {
        case "handoff_recovered": {
            return onRecovered(session, input.recovery, input.at);
        }
        case "tick": {
            return onRecoveringTick(session, input.at);
        }
        case "leave": {
            return endRecovery(session, { kind: "left" });
        }
        default: {
            return unchanged(session);
        }
    }
}

/**
 * Begin a session at logical time `at` from the lobby's handoff, or, when the tab holds none, by asking the lobby for
 * the player's game.
 */
export function startSession(
    gameId: string,
    handoff: GameSessionData | null,
    at: number,
): SessionStep {
    if (handoff === null) {
        const recovering: RecoveringSession = {
            failedLookups: 0,
            gameId,
            retryAt: null,
            status: "recovering",
        };
        return { effects: [{ type: "recover_handoff" }], state: recovering };
    }
    return joinWith(gameId, handoff, at);
}

/**
 * When the session next needs a tick: the earlier of its socket's connect deadline and its pending retry, a failed
 * lookup's retry, or null.
 */
export function sessionDeadline(state: SessionState): number | null {
    if (state.status === "ended") {
        return null;
    }
    if (state.status === "recovering") {
        return state.retryAt;
    }
    const due = [state.connectDeadline, state.retry?.dueAt ?? null].filter((at) => at !== null);
    return due.length === 0 ? null : Math.min(...due);
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
    if (state.status === "recovering") {
        return stepRecovering(state, input);
    }
    return stepActive(state, input);
}

function stepActive(state: ActiveSession, input: SessionInput): SessionStep {
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
        case "handoff_recovered": {
            return unchanged(state);
        }
        default: {
            return assertNever(input);
        }
    }
}
