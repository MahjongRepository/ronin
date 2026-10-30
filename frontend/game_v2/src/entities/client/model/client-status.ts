import {
    type SessionStatusDisplay,
    describePlayerSessionStatus,
    describeSessionStatus,
} from "@/entities/session";

import { type LiveClient } from "./types";

/** The session's status line for a live client's state, in the machine's own terms, for the debug view. */
export function describeClientStatus(state: LiveClient): SessionStatusDisplay {
    return describeSessionStatus(state.session);
}

/** The session's status in a player's terms, for the live page and its rotate panel. */
export function describePlayerClientStatus(state: LiveClient): SessionStatusDisplay {
    return describePlayerSessionStatus(state.session);
}
