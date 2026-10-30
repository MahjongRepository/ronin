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
    answersIdentity,
    isRefusal,
    isResendable,
    isTerminalClose,
    lookupRetryDelayMs,
    retryDelayMs,
} from "./policy";
import {
    type ActiveSession,
    type AwaitingRetrySession,
    type ConnectingSession,
    type EndReason,
    type EndedSession,
    type IdentifyingSession,
    type Identity,
    type PlayingSession,
    type RecoveringSession,
    type RetryKind,
    type SeekingSession,
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

function identityMessage({ handoff, identity }: SeekingSession): ClientMessage {
    return identity.kind === "join"
        ? buildJoinGameMessage(handoff.gameTicket)
        : buildReconnectMessage(handoff.gameTicket);
}

/** Whether the session has a socket open or opening: connecting, identifying or playing. */
export function hasSocket(state: SessionState): boolean {
    return (
        state.status === "connecting" ||
        state.status === "identifying" ||
        state.status === "playing"
    );
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
    if (hasSocket(session) && reason.kind !== "game_ended") {
        effects.push({ type: "close_socket" });
    }
    effects.push(...endEffects(session.gameId, reason));
    const state: EndedSession = { gameId: session.gameId, reason, status: "ended" };
    return { effects, state };
}

/** End a session whose socket just dropped, so there is none to close. */
function endDropped(gameId: string, reason: EndReason): SessionStep {
    return { effects: endEffects(gameId, reason), state: { gameId, reason, status: "ended" } };
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

/** The end of a spent retry budget: the game had started with the seat when the session claims it with RECONNECT. */
function retriesExhausted(identity: Identity, retry: RetryKind): EndReason {
    return { gameStarted: identity.kind === "reconnect", kind: "retries_exhausted", retry };
}

/** Resend the identity message on the open socket after a session retry's wait, or end once its budget is spent. */
function scheduleSessionRetry(session: IdentifyingSession, at: number): SessionStep {
    const attempt = session.attempts.session + 1;
    const delayMs = retryDelayMs("session", attempt);
    if (delayMs === null) {
        return endSession(session, retriesExhausted(session.identity, "session"));
    }
    return unchanged({
        ...session,
        attempts: { ...session.attempts, session: attempt },
        sessionRetryAt: at + delayMs,
    });
}

/** What any state seeking the seat carries on to the next one. */
type Seeker = Pick<SeekingSession, "gameId" | "handoff" | "identity" | "attempts">;

/** Open a socket for the session, which counts as a failed connection unless it opens by its connect deadline. */
function openSocket({ attempts, gameId, handoff, identity }: Seeker, at: number): SessionStep {
    const connecting: ConnectingSession = {
        attempts,
        connectDeadline: at + CONNECT_TIMEOUT_MS,
        gameId,
        handoff,
        identity,
        status: "connecting",
    };
    return { effects: [{ type: "open_socket", url: handoff.wsUrl }], state: connecting };
}

/** Hold the seat: the retries spent seeking it no longer count. */
function admit({ gameId, handoff }: IdentifyingSession, gameStarted: boolean): SessionStep {
    return unchanged({ gameId, gameStarted, handoff, status: "playing" });
}

function onTransportOpened(session: ActiveSession): SessionStep {
    if (session.status !== "connecting") {
        return unchanged(session);
    }
    const identifying: IdentifyingSession = {
        attempts: session.attempts,
        gameId: session.gameId,
        handoff: session.handoff,
        identity: session.identity,
        sessionRetryAt: null,
        status: "identifying",
    };
    return {
        effects: [{ message: identityMessage(identifying), type: "send" }],
        state: identifying,
    };
}

/**
 * A drop of a linked session: a terminal close ends it, any other awaits a transport retry, which replaces a waiting
 * session retry, since the reopened socket sends the identity message itself. A seat held until now is lost.
 */
function onTransportClosed(
    session: ActiveSession,
    { at, code, reason }: Extract<SessionInput, { kind: "transport_closed" }>,
): SessionStep {
    if (!hasSocket(session)) {
        return unchanged(session);
    }
    if (isTerminalClose(code)) {
        return endDropped(session.gameId, { code, kind: "closed", reason });
    }
    return awaitTransportRetry(seekerAfterDrop(session), at);
}

/**
 * What a drop leaves seeking the seat: a seat held until now is lost, claimed back afresh with RECONNECT once the game
 * started, else with JOIN_GAME, which a game waiting to start takes (and one that started meanwhile turns into
 * RECONNECT).
 */
function seekerAfterDrop(session: ActiveSession): Seeker {
    if (session.status !== "playing") {
        return session;
    }
    const { gameId, gameStarted, handoff } = session;
    const identity: Identity = gameStarted
        ? { kind: "reconnect", lostSeat: true }
        : { kind: "join" };
    return { attempts: NO_ATTEMPTS, gameId, handoff, identity };
}

/** Reopen the socket after a transport retry's wait, or end once its budget is spent. */
function awaitTransportRetry(seeker: Seeker, at: number): SessionStep {
    const attempt = seeker.attempts.transport + 1;
    const delayMs = retryDelayMs("transport", attempt);
    if (delayMs === null) {
        return endDropped(seeker.gameId, retriesExhausted(seeker.identity, "transport"));
    }
    const awaiting: AwaitingRetrySession = {
        attempts: { ...seeker.attempts, transport: attempt },
        dueAt: at + delayMs,
        gameId: seeker.gameId,
        handoff: seeker.handoff,
        identity: seeker.identity,
        status: "awaiting_retry",
    };
    return unchanged(awaiting);
}

/** A socket that has not opened by its connect deadline: closed, and taken as a failed connection to retry. */
function onConnectTimeout(session: ConnectingSession, at: number): SessionStep {
    const step = onTransportClosed(session, {
        at,
        code: CONNECT_TIMEOUT_CLOSE.code,
        kind: "transport_closed",
        reason: CONNECT_TIMEOUT_CLOSE.reason,
    });
    return { effects: [{ type: "close_socket" }, ...step.effects], state: step.state };
}

/** Resend the identity message on the open socket once the session retry is due. */
function onIdentifyingTick(session: IdentifyingSession, at: number): SessionStep {
    if (session.sessionRetryAt === null || at < session.sessionRetryAt) {
        return unchanged(session);
    }
    const due: IdentifyingSession = { ...session, sessionRetryAt: null };
    return { effects: [{ message: identityMessage(due), type: "send" }], state: due };
}

/**
 * Run the state's deadline once it is due: give up on a socket that never opened, resend the identity message after a
 * session retry's wait, or reopen the socket after a drop's.
 */
function onTick(session: ActiveSession, at: number): SessionStep {
    switch (session.status) {
        case "connecting": {
            return at >= session.connectDeadline
                ? onConnectTimeout(session, at)
                : unchanged(session);
        }
        case "identifying": {
            return onIdentifyingTick(session, at);
        }
        case "awaiting_retry": {
            return at >= session.dueAt ? openSocket(session, at) : unchanged(session);
        }
        case "playing": {
            return unchanged(session);
        }
        default: {
            return assertNever(session);
        }
    }
}

/**
 * Answer a session error. A refusal ends the session. The others answer an identity message, so only an identifying
 * session takes them: `join_game_already_started` turns a JOIN_GAME into RECONNECT, and `reconnect_retry_later` (to a
 * RECONNECT) or a rate limit resends the identity message after a session retry, as does `not_in_game` while
 * identifying, the answer to an out-of-step client's resync request on a socket that holds no seat. Any other answer
 * to the identity message admits nothing and is never followed by one that does, so it ends the session as refused
 * rather than leave it identifying for good.
 */
function onSessionError(session: ActiveSession, code: string, at: number): SessionStep {
    if (session.status === "identifying" && code === SESSION_ERROR_CODE.NOT_IN_GAME) {
        return scheduleSessionRetry(session, at);
    }
    if (isRefusal(code)) {
        return endSession(session, { code, kind: "refused" });
    }
    return session.status === "identifying"
        ? onIdentityAnswer(session, code, at)
        : unchanged(session);
}

/** Answer a session error to an identifying session's identity message that is not a refusal. */
function onIdentityAnswer(session: IdentifyingSession, code: string, at: number): SessionStep {
    if (code === SESSION_ERROR_CODE.JOIN_GAME_ALREADY_STARTED) {
        return session.identity.kind === "join" ? resumeStartedGame(session) : unchanged(session);
    }
    const retriesIdentity =
        (code === SESSION_ERROR_CODE.RECONNECT_RETRY_LATER &&
            session.identity.kind === "reconnect") ||
        isResendable(code);
    if (retriesIdentity) {
        return scheduleSessionRetry(session, at);
    }
    return answersIdentity(code)
        ? endSession(session, { code, kind: "refused" })
        : unchanged(session);
}

/** A JOIN_GAME refused because the game already started with the seat: claim it with RECONNECT on the same socket. */
function resumeStartedGame(session: IdentifyingSession): SessionStep {
    const resuming: IdentifyingSession = {
        ...session,
        identity: { kind: "reconnect", lostSeat: false },
        sessionRetryAt: null,
    };
    return { effects: [{ message: identityMessage(resuming), type: "send" }], state: resuming };
}

/**
 * Take a server message. Only an open socket carries one, so a session connecting or awaiting a transport retry
 * ignores it; a session error is answered, and the game's end ends the session.
 */
function onMessage(session: ActiveSession, message: ParsedServerMessage, at: number): SessionStep {
    if (session.status === "connecting" || session.status === "awaiting_retry") {
        return unchanged(session);
    }
    if (message.type === "session_error") {
        return onSessionError(session, message.code, at);
    }
    if (message.type === "game_end") {
        return endSession(session, { kind: "game_ended" });
    }
    return session.status === "playing"
        ? onPlayingMessage(session, message)
        : onIdentifyingMessage(session, message);
}

/** The game's start, or a snapshot of it, tells a joined session waiting for it that the game started. */
function onPlayingMessage(session: PlayingSession, message: ParsedServerMessage): SessionStep {
    const starts = message.type === "game_started" || message.type === "game_reconnected";
    return starts && !session.gameStarted
        ? unchanged({ ...session, gameStarted: true })
        : unchanged(session);
}

/**
 * The server's answer admits an identifying session: `game_joined` a JOIN_GAME, the snapshot a RECONNECT. No other
 * message does, since the server answers the identity message ahead of anything the game sends the seat.
 */
function onIdentifyingMessage(
    session: IdentifyingSession,
    message: ParsedServerMessage,
): SessionStep {
    if (message.type === "game_reconnected") {
        return admit(session, true);
    }
    const joined = message.type === "game_joined" && session.identity.kind === "join";
    return joined ? admit(session, false) : unchanged(session);
}

function joinWith(gameId: string, handoff: GameSessionData, at: number): SessionStep {
    return openSocket({ attempts: NO_ATTEMPTS, gameId, handoff, identity: { kind: "join" } }, at);
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
 * When the session next needs a tick: its socket's connect deadline, its session retry, its transport retry, a failed
 * lookup's retry, or null.
 */
export function sessionDeadline(state: SessionState): number | null {
    switch (state.status) {
        case "recovering": {
            return state.retryAt;
        }
        case "connecting": {
            return state.connectDeadline;
        }
        case "identifying": {
            return state.sessionRetryAt;
        }
        case "awaiting_retry": {
            return state.dueAt;
        }
        case "playing":
        case "ended": {
            return null;
        }
        default: {
            return assertNever(state);
        }
    }
}

/** Whether this page held the seat and lost it to a drop, and has not held it again since. */
export function hasLostSeat(state: SessionState): boolean {
    switch (state.status) {
        case "connecting":
        case "identifying":
        case "awaiting_retry": {
            return state.identity.kind === "reconnect" && state.identity.lostSeat;
        }
        case "recovering":
        case "playing":
        case "ended": {
            return false;
        }
        default: {
            return assertNever(state);
        }
    }
}

/**
 * End the session because its driver failed while stepping it or running its effects, replacing any end it had
 * reached: the end stays on the page, showing the failure, and the driver closes the socket itself.
 */
export function failSession(state: SessionState, detail: string): SessionState {
    return { gameId: state.gameId, reason: { detail, kind: "failed" }, status: "ended" };
}

/**
 * The session transition: the next state and the effects it asks for, with no IO, timer or clock read inside. An
 * input a state has no rule for leaves it as it is and emits nothing: a tick before its deadline, a socket opening or
 * closing the state is not waiting on, a message while no socket is open, the lobby's answer outside recovering. An
 * ended session ignores every input but a leave from an end that stayed on the page.
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
