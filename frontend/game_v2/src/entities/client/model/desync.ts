import { type SessionState, failSession, hasSocket } from "@/entities/session";
import { type TableEvent, applyEvent } from "@/entities/table";
import {
    type ParsedServerMessage,
    SESSION_ERROR_CODE,
    SESSION_MESSAGE_TYPE,
    buildResyncMessage,
} from "@/shared/protocol";

import { type ClientStep, type Desync, type DesyncCause, type GameClientState } from "./types";

const LOST_STEP: TableEvent = { type: "lost_step" };

/** How long a resync request waits for its snapshot before the client asks again. */
export const RESYNC_ANSWER_MS = 10_000;

/** The resync requests a page may send in all: the next loss of step past them ends the page. */
export const MAX_RESYNC_REQUESTS = 5;

/** How soon a resync refused before the first deal is asked again when the deal's time is unknown or past. */
const NOT_STARTED_RETRY_MS = 1000;

/** Whether the client can send on its session: it holds the seat, which only an open socket does. */
export function canSend(session: SessionState | null): boolean {
    return session?.status === "playing";
}

/**
 * Whether the client takes server messages on its session at all: a replay's (none) and a session on an open socket,
 * identifying or playing, as the session itself does. Any other has no open socket, so any message then is dropped.
 */
export function takesServerMessages(session: SessionState | null): boolean {
    return session === null || session.status === "identifying" || session.status === "playing";
}

/** End the client because its driver failed while stepping it; nothing is pending afterwards. */
export function failGameClient(state: GameClientState, detail: string): GameClientState {
    const session = state.session === null ? null : failSession(state.session, detail);
    return { ...state, calls: null, decision: null, notice: null, roundConfirm: null, session };
}

/** End the client as failed from inside a step, on the page as a driver failure does, closing its socket. */
function failStep(state: GameClientState, detail: string): ClientStep {
    const linked = state.session !== null && hasSocket(state.session);
    return {
        effects: linked ? [{ type: "close_socket" }] : [],
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
 * until now, puts the client out of step. Answering freezes: the open decision and an owed or sent round confirm go,
 * since the snapshot and the wait the server re-sends after it say again what the seat owes, and nothing sent is
 * ever sent again; the table knows its round history may miss what follows. Out of step already, the failure is one
 * more message dropped.
 */
export function desyncStep(state: GameClientState, cause: DesyncCause, detail: string): ClientStep {
    const effects = [{ detail, type: "report_protocol_failure" } as const];
    const counted = { ...state, unreadMessages: state.unreadMessages + 1 };
    if (state.desync !== null) {
        return { effects, state: counted };
    }
    const { roundConfirm } = state;
    return {
        effects,
        state: {
            ...counted,
            decision: null,
            desync: { answerDue: null, cause, detail, since: state.now },
            roundConfirm: roundConfirm?.kind === "final" ? roundConfirm : null,
            table: applyEvent(state.table, LOST_STEP),
        },
    };
}

/**
 * A snapshot that does not parse (an incomplete one included) or that the client cannot take, or a game's end it
 * cannot take while out of step: no fresh snapshot can rebuild a client that cannot take one, so the page ends as
 * failed, out of step with the server, which it stays if it was already.
 */
export function recoveryFailedStep(
    state: GameClientState,
    cause: DesyncCause,
    detail: string,
): ClientStep {
    const lost = desyncStep(state, cause, detail);
    const failed = failStep(lost.state, `The server's game state could not be shown: ${detail}`);
    return { effects: [...lost.effects, ...failed.effects], state: failed.state };
}

/**
 * The out-of-step client after a message it drops: when it says the game has not dealt yet (a resync refused in the
 * game start pause), the client asks again
 * when the first deal is due, or shortly when that time is unknown or past, rather than a whole answer's wait later,
 * which would eat into a first dealer's turn.
 */
export function deferredUntilDeal(
    state: GameClientState,
    message: ParsedServerMessage,
): GameClientState {
    const { desync, firstDealDue, now } = state;
    const notStarted =
        message.type === "session_error" && message.code === SESSION_ERROR_CODE.GAME_NOT_STARTED;
    if (desync === null || !notStarted) {
        return state;
    }
    const answerDue =
        firstDealDue !== null && firstDealDue > now ? firstDealDue : now + NOT_STARTED_RETRY_MS;
    return { ...state, desync: { ...desync, answerDue } };
}

/** The client a snapshot rebuilt: in step again, and the failures before it no longer count. */
export function resynced(state: GameClientState): GameClientState {
    return { ...state, desync: null, unreadMessages: 0 };
}

/**
 * Whether an out-of-step client can ask its session's server for a snapshot: on an open socket, the session playing
 * or identifying with no session retry waiting, since a socket whose identity message the server refused holds no
 * seat to resync until the retry resends it. Identifying, only the request is sent, never an answer to the game.
 */
function canRequestResync(session: SessionState | null): boolean {
    return (
        session?.status === "playing" ||
        (session?.status === "identifying" && session.sessionRetryAt === null)
    );
}

/**
 * Ask an out-of-step client's server for a fresh snapshot once it holds the seat and has no request outstanding, or
 * its request went unanswered past its due time. A dropped socket forgets the request, since its reconnect brings a
 * snapshot of its own. While the reopened socket identifies, that snapshot is the request's answer: the client asks
 * only once it goes unanswered for `RESYNC_ANSWER_MS` (a snapshot frame that did not decode), on the same socket, which
 * a RECONNECT the server took binds. The requests are counted for the page, whatever the session's own retries reset:
 * one past `MAX_RESYNC_REQUESTS` ends the page as failed.
 */
export function settleDesync(step: ClientStep): ClientStep {
    const { state } = step;
    const { desync } = state;
    if (desync === null) {
        return step;
    }
    const answerDue = awaitedAnswerDue(state, desync);
    if (answerDue !== desync.answerDue) {
        return { ...step, state: { ...state, desync: { ...desync, answerDue } } };
    }
    const due = answerDue === null || state.now >= answerDue;
    return canRequestResync(state.session) && due ? requestResync(step, desync) : step;
}

/**
 * When an out-of-step client's snapshot counts as unanswered before it sends a request: none with no socket to ask
 * on (the request forgotten), `RESYNC_ANSWER_MS` from now for an identifying session's own snapshot, else as it was.
 */
function awaitedAnswerDue(state: GameClientState, desync: Desync): number | null {
    if (!canRequestResync(state.session)) {
        return null;
    }
    if (desync.answerDue === null && !canSend(state.session)) {
        return state.now + RESYNC_ANSWER_MS;
    }
    return desync.answerDue;
}

/** Send a resync request after `step`, or end the page once the page's requests are spent. */
function requestResync(step: ClientStep, desync: Desync): ClientStep {
    const { state } = step;
    if (state.resyncRequests >= MAX_RESYNC_REQUESTS) {
        const detail = `Lost step with the server ${MAX_RESYNC_REQUESTS} times: ${desync.detail}`;
        const failed = failStep(state, detail);
        return { effects: [...step.effects, ...failed.effects], state: failed.state };
    }
    return {
        effects: [...step.effects, { message: buildResyncMessage(), type: "send" }],
        state: {
            ...state,
            desync: { ...desync, answerDue: state.now + RESYNC_ANSWER_MS },
            resyncRequests: state.resyncRequests + 1,
        },
    };
}

/** When an out-of-step client's resync request counts as unanswered, or null. */
export function desyncDeadline(state: GameClientState): number | null {
    return canRequestResync(state.session) ? (state.desync?.answerDue ?? null) : null;
}
