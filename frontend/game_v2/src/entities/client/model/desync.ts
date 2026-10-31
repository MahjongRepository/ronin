import { type SessionState, failSession, hasSocket } from "@/entities/session";
import { type TableEvent, applyEvent } from "@/entities/table";
import { assertNever } from "@/shared/lib";
import {
    type ParsedServerMessage,
    SESSION_ERROR_CODE,
    SESSION_MESSAGE_TYPE,
    buildResyncMessage,
} from "@/shared/protocol";

import { settledPending } from "./pending";
import {
    type ClientStep,
    type Desync,
    type DesyncCause,
    type LiveClient,
    type ResyncRequest,
} from "./types";

const LOST_STEP: TableEvent = { type: "lost_step" };

const UNSENT: ResyncRequest = { kind: "unsent" };

/** How long a resync request waits for its snapshot before the client asks again. */
export const RESYNC_ANSWER_MS = 10_000;

/** The resync requests a page may send in all: the next loss of step past them ends the page. */
export const MAX_RESYNC_REQUESTS = 5;

const MS_PER_SECOND = 1000;

/** Where the client stands since it lost step with the server, or null while in step. */
export function desyncOf(state: LiveClient): Desync | null {
    return state.sync.kind === "out_of_step" ? state.sync : null;
}

/** Whether the client can send on its session: it holds the seat, which only an open socket does. */
export function canSend(session: SessionState): boolean {
    return session.status === "playing";
}

/**
 * Whether the client takes server messages on its session at all: on an open socket, identifying or playing, as the
 * session itself does. Any other has no open socket, so any message then is dropped.
 */
export function takesServerMessages(session: SessionState): boolean {
    return session.status === "identifying" || session.status === "playing";
}

/** End the client because its driver failed while stepping it; nothing is pending or shown afterwards. */
export function failGameClient(state: LiveClient, detail: string): LiveClient {
    const session = failSession(state.session, detail);
    return settledPending({ ...state, calls: null, notice: null, session, showsLastResult: false });
}

/** End the client as failed from inside a step, on the page as a driver failure does, closing its socket. */
function failStep(state: LiveClient, detail: string): ClientStep<LiveClient> {
    return {
        effects: hasSocket(state.session) ? [{ type: "close_socket" }] : [],
        state: failGameClient(state, detail),
    };
}

/** Whether a server payload is the snapshot, whether or not it parses. */
export function isSnapshotPayload(raw: Readonly<Record<string, unknown>>): boolean {
    return raw.type === SESSION_MESSAGE_TYPE.GAME_RECONNECTED;
}

/**
 * Whether an out-of-step client takes a message: the snapshot that rebuilds it, and the game's end, after which no
 * snapshot comes, with the round end before it, the game's last, which carries no wait: both carry the scores and the
 * result the server settled, so the page ends on them, its ledger marked incomplete (the table's
 * `roundHistoryInStep`). Every other message builds on the table it lost, so it is dropped.
 */
export function takesWhileDesynced(message: ParsedServerMessage): boolean {
    return (
        message.type === "game_reconnected" ||
        message.type === "game_end" ||
        (message.type === "round_end" && message.waitId === null)
    );
}

/**
 * The client after a protocol failure, reported for the console: it counts towards the board's notice and, in step
 * until now, puts the client out of step, which owes nothing: the snapshot and the wait the server re-sends after it
 * say again what the seat owes, and nothing sent is ever sent again; the table knows its round history may miss what
 * follows. Out of step already, the failure is one more message dropped.
 */
export function desyncStep(
    state: LiveClient,
    cause: DesyncCause,
    detail: string,
): ClientStep<LiveClient> {
    const effects = [{ detail, type: "report_protocol_failure" } as const];
    const { now, sync, table } = state;
    if (sync.kind === "out_of_step") {
        const counted: Desync = { ...sync, unreadMessages: sync.unreadMessages + 1 };
        return { effects, state: { ...state, sync: counted } };
    }
    const desync: Desync = {
        cause,
        detail,
        kind: "out_of_step",
        request: UNSENT,
        since: now,
        unreadMessages: 1,
    };
    return { effects, state: { ...state, sync: desync, table: applyEvent(table, LOST_STEP) } };
}

/**
 * A snapshot that does not parse (an incomplete one included) or that the client cannot take: no fresh snapshot can
 * rebuild a client that cannot take one, so the page ends as failed, out of step with the server, which it stays if
 * it was already.
 */
export function recoveryFailedStep(
    state: LiveClient,
    cause: DesyncCause,
    detail: string,
): ClientStep<LiveClient> {
    const lost = desyncStep(state, cause, detail);
    const failed = failStep(lost.state, `The server's game state could not be shown: ${detail}`);
    return { effects: [...lost.effects, ...failed.effects], state: failed.state };
}

/**
 * The out-of-step client after a message it drops. One saying the game has not dealt yet (a resync refused while the
 * game waits for its players or in its start pause) answers the request: the client asks again when the first deal
 * is due, rather than a whole answer's wait later, which would eat into a first dealer's turn; where no deal time lies
 * ahead, it waits for the server's next game message instead of asking on a timer, which would spend the page's
 * requests however long the game waits to start. Waiting so, a game start names the deal's time, and any other game
 * message says the game moved, so the client asks at once.
 */
export function deferredUntilDeal(
    state: LiveClient,
    sync: Desync,
    message: ParsedServerMessage,
): LiveClient {
    if (message.type === "session_error" && message.code === SESSION_ERROR_CODE.GAME_NOT_STARTED) {
        return withRequest(state, sync, awaitingDeal(state));
    }
    const gameMoved = message.type !== "session_error" && message.type !== "error";
    return sync.request.kind === "on_game_message" && gameMoved
        ? movedOn(state, sync, message)
        : state;
}

function withRequest(state: LiveClient, sync: Desync, request: ResyncRequest): LiveClient {
    return { ...state, sync: { ...sync, request } };
}

/** The request of a client told the game has not dealt: at the first deal's time ahead, else on the next game message. */
function awaitingDeal(state: LiveClient): ResyncRequest {
    const { firstDealDue, now } = state;
    return firstDealDue !== null && firstDealDue > now
        ? { due: firstDealDue, kind: "at_deal" }
        : { kind: "on_game_message" };
}

/**
 * The client awaiting the deal after a game message: at the deal's time a game start names, else at once. The game
 * start's timer settings are kept too, so the socket's silence limit covers its pause.
 */
function movedOn(state: LiveClient, sync: Desync, message: ParsedServerMessage): LiveClient {
    if (message.type !== "game_started" || message.timer === null) {
        return withRequest(state, sync, UNSENT);
    }
    const { timer } = message;
    const dealDue = state.now + timer.gameStartPauseSeconds * MS_PER_SECOND;
    const waiting = withRequest(state, sync, { due: dealDue, kind: "at_deal" });
    return { ...waiting, firstDealDue: dealDue, timer };
}

/**
 * Whether a message is the rate limit's refusal of the client's own outstanding resync request: the endpoint answers
 * an over-budget RESYNC with the same code as an over-budget identity message, so while a request is outstanding the
 * refusal is the request's, which is asked again when its answer comes due, and the session never takes it for its
 * identity message's, which it would resend on a socket that may hold the seat already.
 */
export function refusesResyncRequest(state: LiveClient, message: ParsedServerMessage): boolean {
    return (
        state.sync.kind === "out_of_step" &&
        state.sync.request.kind === "sent" &&
        message.type === "session_error" &&
        message.code === SESSION_ERROR_CODE.RATE_LIMITED
    );
}

/**
 * The client a snapshot rebuilds, before it takes the snapshot: in step again, owing nothing yet, and the failures
 * before it no longer count. One in step already keeps what it owes, which the snapshot may repeat.
 */
export function resynced(state: LiveClient): LiveClient {
    return state.sync.kind === "in_step"
        ? state
        : { ...state, sync: { kind: "in_step", pending: null } };
}

/**
 * Whether an out-of-step client can ask its session's server for a snapshot: on an open socket, the session playing
 * or identifying with no session retry waiting, since a socket whose identity message the server refused holds no
 * seat to resync until the retry resends it. Identifying, only the request is sent, never an answer to the game.
 */
function canRequestResync(session: SessionState): boolean {
    return (
        session.status === "playing" ||
        (session.status === "identifying" && session.sessionRetryAt === null)
    );
}

/**
 * Ask an out-of-step client's server for a fresh snapshot once it holds the seat and has no request outstanding, or
 * its request went unanswered past its due time. A dropped socket forgets the request, and any wait for the deal,
 * since its reconnect brings a snapshot of its own. While the reopened socket identifies, that snapshot is the
 * request's answer: the client asks only once it goes unanswered for `RESYNC_ANSWER_MS` (a snapshot frame that did not
 * decode), on the same socket, which a RECONNECT the server took binds. The requests are counted for the page,
 * whatever the session's own retries reset: one past `MAX_RESYNC_REQUESTS` ends the page as failed. A client awaiting
 * the deal asks nothing until a game message comes (`deferredUntilDeal`).
 */
export function settleDesync(step: ClientStep<LiveClient>): ClientStep<LiveClient> {
    const { state } = step;
    const { session, sync } = state;
    if (sync.kind === "in_step") {
        return step;
    }
    if (canRequestResync(session)) {
        return settledRequest(step, sync);
    }
    return sync.request.kind === "unsent"
        ? step
        : { ...step, state: withRequest(state, sync, UNSENT) };
}

/**
 * An out-of-step client that can ask, by where its request stands: unsent, it asks at once while it holds the seat, and
 * while it identifies awaits its own snapshot first; any other with a due time asks once that comes.
 */
function settledRequest(step: ClientStep<LiveClient>, sync: Desync): ClientStep<LiveClient> {
    const { state } = step;
    const { request } = sync;
    switch (request.kind) {
        case "unsent": {
            if (canSend(state.session)) {
                return requestResync(step, sync);
            }
            const due = state.now + RESYNC_ANSWER_MS;
            return { ...step, state: withRequest(state, sync, { due, kind: "awaiting_snapshot" }) };
        }
        case "sent":
        case "awaiting_snapshot":
        case "at_deal": {
            return state.now >= request.due ? requestResync(step, sync) : step;
        }
        case "on_game_message": {
            return step;
        }
        default: {
            return assertNever(request);
        }
    }
}

/** Send a resync request after `step`, or end the page once the page's requests are spent. */
function requestResync(step: ClientStep<LiveClient>, desync: Desync): ClientStep<LiveClient> {
    const { state } = step;
    if (state.resyncRequests >= MAX_RESYNC_REQUESTS) {
        const detail = `Lost step with the server ${MAX_RESYNC_REQUESTS} times: ${desync.detail}`;
        const failed = failStep(state, detail);
        return { effects: [...step.effects, ...failed.effects], state: failed.state };
    }
    const sent = withRequest(state, desync, { due: state.now + RESYNC_ANSWER_MS, kind: "sent" });
    return {
        effects: [...step.effects, { message: buildResyncMessage(), type: "send" }],
        state: { ...sent, resyncRequests: state.resyncRequests + 1 },
    };
}

/** When an out-of-step client's resync request counts as unanswered or comes due, or null. */
export function desyncDeadline(state: LiveClient): number | null {
    const { session, sync } = state;
    if (sync.kind === "in_step" || !canRequestResync(session)) {
        return null;
    }
    const { request } = sync;
    return request.kind === "unsent" || request.kind === "on_game_message" ? null : request.due;
}
