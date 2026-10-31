import { NUM_PLAYERS, type TimerSettings } from "@/shared/protocol";
import { DEFAULT_SERVER_SILENCE_LIMIT_MS } from "@/shared/websocket";

import { type LiveClient } from "./types";

const MS_PER_SECOND = 1000;

/**
 * The most pages a round result's advance can wait out in turn, one per winner: every seat but the discarder's, where
 * the game allows that many rons on one discard. The limit covers a result the client may never have read, so it
 * takes the most the rules allow rather than the result's own count.
 */
const MAX_RESULT_PAGES = NUM_PLAYERS - 1;

/** What late timers and a slow network may add to the longest wait before the server speaks again. */
const SILENCE_MARGIN_MS = 25_000;

/**
 * The longest the server can go silent at these timer settings while the connection is healthy: a turn's base and
 * a full bank, a call window, a round result's advance over its pages, or the game start pause, whichever is
 * longest.
 */
function longestWaitSeconds(timer: TimerSettings): number {
    return Math.max(
        timer.baseTurnSeconds + timer.maxBankSeconds,
        timer.meldDecisionSeconds,
        timer.roundAdvanceTimeoutSeconds * MAX_RESULT_PAGES,
        timer.gameStartPauseSeconds,
    );
}

/**
 * How long the client's socket waits for a silent server before it takes the connection for lost: the longest wait
 * the server names plus a margin for late timers, the game's timer settings once it started, before that the pending
 * game's wait for its players that the seat's `game_joined` names. Before either, the socket's own default holds,
 * while the server answers the identity message, which it does at once.
 */
export function serverSilenceLimitMs(state: LiveClient): number {
    const { pendingGameSeconds, timer } = state;
    const waitSeconds = timer === null ? pendingGameSeconds : longestWaitSeconds(timer);
    return waitSeconds === null
        ? DEFAULT_SERVER_SILENCE_LIMIT_MS
        : waitSeconds * MS_PER_SECOND + SILENCE_MARGIN_MS;
}
