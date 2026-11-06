import {
    awaitsSnapshot,
    canRequestResync,
    failSession,
    hasSocket,
    holdsSeat,
} from "@/entities/session";
import { type TableEvent, applyEvent } from "@/entities/table";
import { assertNever } from "@/shared/lib";
import {
    type ParsedServerMessage,
    SESSION_ERROR_CODE,
    SESSION_MESSAGE_TYPE,
    WIRE_KEY,
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

const ON_GAME_MESSAGE: ResyncRequest = { kind: "on_game_message" };

const GAME_MOVED: ResyncRequest = { kind: "game_moved" };

/** How long a resync request waits for its snapshot before the client asks again. */
export const RESYNC_ANSWER_MS = 10_000;

/** The resync requests a page may send in all: the next loss of step past them ends the page. */
export const MAX_RESYNC_REQUESTS = 5;

/** Where the client stands since it lost step with the server, or null while in step. */
export function desyncOf(state: LiveClient): Desync | null {
    return state.sync.kind === "out_of_step" ? state.sync : null;
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
    return raw[WIRE_KEY.SESSION_TYPE] === SESSION_MESSAGE_TYPE.GAME_RECONNECTED;
}

/**
 * Whether an out-of-step client takes a message: the snapshot that rebuilds it, and the game's end, after which no
 * snapshot comes, with the round end before it, the game's last, which carries no wait: both carry the scores and the
 * result the server settled, so the page ends on them, the table marked out of step (`inStep`). Every other message
 * builds on the table it lost, so it is dropped.
 */
export function takesWhileDesynced(message: ParsedServerMessage): boolean {
    return (
        message.type === "game_reconnected" ||
        message.type === "game_end" ||
        (message.type === "round_end" && message.roundAdvance === null)
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
 * The out-of-step client's request after a message it drops. One saying the game has not started (a resync refused
 * while the pending game waits for its players) answers the request: the client waits for the server's next game
 * message instead of asking on a timer, which would spend the page's requests however long the game waits to start.
 * Waiting so, a game message says the game started, so the client asks at once; a session message (the join's
 * answer, an error) says nothing of the game.
 */
export function requestAfterDropped(
    state: LiveClient,
    sync: Desync,
    message: ParsedServerMessage,
): LiveClient {
    if (message.type === "session_error" && message.code === SESSION_ERROR_CODE.GAME_NOT_STARTED) {
        return withRequest(state, sync, ON_GAME_MESSAGE);
    }
    const gameMoved =
        message.type !== "session_error" &&
        message.type !== "error" &&
        message.type !== "game_joined";
    return sync.request.kind === "on_game_message" && gameMoved
        ? withRequest(state, sync, GAME_MOVED)
        : state;
}

function withRequest(state: LiveClient, sync: Desync, request: ResyncRequest): LiveClient {
    return { ...state, sync: { ...sync, request } };
}

/**
 * The client with the pacing a message names kept, in step or out of it: a game start's timer settings and the
 * pending game's wait `game_joined` names, which the socket's silence limit reads, so a dropped game start never cuts
 * the start confirm's wait short.
 */
export function withPacing(state: LiveClient, message: ParsedServerMessage): LiveClient {
    switch (message.type) {
        case "game_started": {
            return { ...state, timer: message.timer ?? state.timer };
        }
        case "game_joined": {
            return { ...state, pendingGameSeconds: message.pendingGameSeconds };
        }
        default: {
            return state;
        }
    }
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
 * Ask an out-of-step client's server for a fresh snapshot once it holds the seat and has no request outstanding, or
 * its request went unanswered past its due time. A session that cannot ask voids the request (`voidedRequest`), so a
 * dropped socket forgets it, and any wait for the game, since its reconnect brings a snapshot of its own. While the
 * reopened socket identifies with RECONNECT, that snapshot is the request's answer: the client asks only once it goes
 * unanswered for `RESYNC_ANSWER_MS` (a snapshot frame that did not decode), on the same socket, which a RECONNECT the
 * server took binds. A JOIN_GAME is answered by `game_joined`, never a snapshot, and only a game that has not started
 * takes one, so the client then waits for the game as a refusal of the game not started would have it. The requests
 * are counted for the page, whatever the session's own retries reset: one past `MAX_RESYNC_REQUESTS` ends the page as
 * failed. A client waiting for the game asks nothing until a game message comes (`requestAfterDropped`).
 */
export function settleDesync(step: ClientStep<LiveClient>): ClientStep<LiveClient> {
    const { state } = step;
    const { session, sync } = state;
    if (sync.kind === "in_step") {
        return step;
    }
    return voidedRequest(canRequestResync(session) ? settledRequest(step, sync) : step);
}

/** The step with its request voided where the session cannot ask, the one place that rule lives. */
function voidedRequest(step: ClientStep<LiveClient>): ClientStep<LiveClient> {
    const { state } = step;
    const { session, sync } = state;
    if (sync.kind === "in_step" || sync.request.kind === "unsent" || canRequestResync(session)) {
        return step;
    }
    return { ...step, state: withRequest(state, sync, UNSENT) };
}

/** The wait for a RECONNECT's own snapshot, asked for only once it goes unanswered for `RESYNC_ANSWER_MS`. */
function snapshotWait(state: LiveClient): ResyncRequest {
    return { due: state.now + RESYNC_ANSWER_MS, kind: "awaiting_snapshot" };
}

/** The request of an unsent client whose identifying socket cannot ask yet: the answer it awaits instead. */
function identifyingRequest(state: LiveClient): ResyncRequest {
    return awaitsSnapshot(state.session) ? snapshotWait(state) : ON_GAME_MESSAGE;
}

/**
 * Whether a request waits on the game, for its next message or asking as it moved, as a JOIN_GAME's socket waits:
 * once the session turns its identity into RECONNECT (`join_game_already_started`), the snapshot that answers it is
 * due instead.
 */
function waitsOnTheGame(request: ResyncRequest): boolean {
    return request.kind === "on_game_message" || request.kind === "game_moved";
}

/**
 * An out-of-step client that can ask, by where its request stands: unsent, it asks at once while it holds the seat, and
 * while it identifies awaits the answer its identity message brings first; a wait on the game turns into the wait for
 * the snapshot once the identity is a RECONNECT; once the game moved it asks at once, identifying or not, since only an
 * admitted socket hears the game; any other with a due time asks once that comes.
 */
function settledRequest(step: ClientStep<LiveClient>, sync: Desync): ClientStep<LiveClient> {
    const { state } = step;
    const { request } = sync;
    if (awaitsSnapshot(state.session) && waitsOnTheGame(request)) {
        return { ...step, state: withRequest(state, sync, snapshotWait(state)) };
    }
    switch (request.kind) {
        case "unsent": {
            return holdsSeat(state.session)
                ? requestResync(step, sync)
                : { ...step, state: withRequest(state, sync, identifyingRequest(state)) };
        }
        case "game_moved": {
            return requestResync(step, sync);
        }
        case "sent":
        case "awaiting_snapshot": {
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
    const { sync } = state;
    if (sync.kind === "in_step") {
        return null;
    }
    const { request } = sync;
    return request.kind === "sent" || request.kind === "awaiting_snapshot" ? request.due : null;
}
