import { type SessionState, hasEnded, hasLostSeat, holdsSeat } from "@/entities/session";
import { type ParsedServerMessage } from "@/shared/protocol";

import { refusalOf } from "./decision";
import { decisionOf, roundConfirmOf } from "./pending";
import { type LiveClient, type TimedNotice } from "./types";

const RECONNECTED_NOTICE_MS = 3000;
const REFUSED_NOTICE_MS = 4000;

/**
 * The timed notice a session keeps: none once it ended, and the seat's return only while the seat is held, so a
 * second drop replaces it with its own notice.
 */
export function keptNotice(notice: TimedNotice | null, session: SessionState): TimedNotice | null {
    if (hasEnded(session)) {
        return null;
    }
    return notice?.kind === "reconnected" && !holdsSeat(session) ? null : notice;
}

/**
 * The wait id of the request the client submitted and awaits an answer to, or null: a submitted decision's, else a
 * sent round confirm's.
 */
export function submittedWaitId(state: LiveClient): number | null {
    const decision = decisionOf(state);
    const roundConfirm = roundConfirmOf(state);
    if (decision?.status.kind === "submitted") {
        return decision.waitId;
    }
    return roundConfirm?.kind === "sent" ? roundConfirm.waitId : null;
}

/**
 * What the client stood on before a message: the session it found, and the wait id of the request it had submitted
 * (`submittedWaitId`).
 */
export interface NoticeBefore {
    readonly session: SessionState;
    readonly submitted: number | null;
}

/**
 * The notice a message raises, from where the client stood before it (`before`) and the session it left (`state`'s):
 * the seat is back after a reconnect's snapshot, when this page lost it to a drop; a move refused while the seat
 * plays, only when the refusal names the submitted request's wait id, the match that reopens it. Null for any other
 * message.
 */
function messageNotice(
    before: NoticeBefore,
    state: LiveClient,
    message: ParsedServerMessage,
): TimedNotice | null {
    const { now, session } = state;
    if (message.type === "game_reconnected") {
        const lostSeat = hasLostSeat(before.session);
        return lostSeat ? { kind: "reconnected", until: now + RECONNECTED_NOTICE_MS } : null;
    }
    const refusal = refusalOf(message);
    if (!holdsSeat(session) || refusal === null || refusal.waitId !== before.submitted) {
        return null;
    }
    return { code: refusal.code, kind: "refused", until: now + REFUSED_NOTICE_MS };
}

/** The notices a message leaves: the one it raises, if any, else the one shown. */
export function withNotice(
    before: NoticeBefore,
    state: LiveClient,
    message: ParsedServerMessage,
): LiveClient {
    const notice = messageNotice(before, state, message);
    return notice === null ? state : { ...state, notice };
}
