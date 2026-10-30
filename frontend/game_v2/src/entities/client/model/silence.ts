import { type TimerSettings } from "@/shared/protocol";
import { DEFAULT_SERVER_SILENCE_LIMIT_MS } from "@/shared/websocket";

import { type LiveClient } from "./types";

const MS_PER_SECOND = 1000;

/** The pages a round result's advance can wait out in turn: a double ron's two winners. */
const MAX_RESULT_PAGES = 2;

/** What late timers and a slow network may add to the longest wait before the server speaks again. */
const SILENCE_MARGIN_MS = 25_000;

/**
 * The longest the server can go silent at these timer settings while the connection is healthy: a turn's base and
 * a full bank, a call window, a round result's advance over its pages, or the game start pause, whichever is
 * longest, and a margin for late timers.
 */
function longestSilenceMs(timer: TimerSettings): number {
    const longestWaitSeconds = Math.max(
        timer.baseTurnSeconds + timer.maxBankSeconds,
        timer.meldDecisionSeconds,
        timer.roundAdvanceTimeoutSeconds * MAX_RESULT_PAGES,
        timer.gameStartPauseSeconds,
    );
    return longestWaitSeconds * MS_PER_SECOND + SILENCE_MARGIN_MS;
}

/**
 * How long the client's socket waits for a silent server before it takes the connection for lost: long enough for
 * the longest wait the game's timer settings allow, never shorter than the default before they arrive (the server may
 * hold a game that waits for its players that long before it starts).
 */
export function serverSilenceLimitMs(state: LiveClient): number {
    const { timer } = state;
    return timer === null
        ? DEFAULT_SERVER_SILENCE_LIMIT_MS
        : Math.max(DEFAULT_SERVER_SILENCE_LIMIT_MS, longestSilenceMs(timer));
}
