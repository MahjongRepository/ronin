import { type CancelTimer } from "@/shared/clock";
import { type ObserveAnswer, REPLAY_VERSION, decodeObserveAnswer } from "@/shared/protocol";

/** A replay's binary records, or the HTTP status the server refused it with. */
export type ReplayFetch =
    | { readonly ok: true; readonly content: Uint8Array }
    | { readonly ok: false; readonly status: number };

/** Fetch a replay; rejects on a network failure, and with an `AbortError` once `signal` aborts. */
export type LoadReplay = (gameId: string, signal: AbortSignal) => Promise<ReplayFetch>;

const HTTP_NOT_FOUND = 404;

/**
 * The waits before asking again for a replay the server has not stored yet: the game end reaches the players before
 * the server saves it (`docs/architecture.md`, Replays), so a link from the game's end may race it.
 */
export const REPLAY_NOT_FOUND_RETRY_MS = [500, 1000, 2000] as const;

export async function fetchReplay(gameId: string, signal: AbortSignal): Promise<ReplayFetch> {
    const url = `/api/replays/${encodeURIComponent(gameId)}?v=${encodeURIComponent(REPLAY_VERSION)}`;
    const response = await fetch(url, { signal });
    if (!response.ok) {
        return { ok: false, status: response.status };
    }
    return { content: new Uint8Array(await response.arrayBuffer()), ok: true };
}

/** An answer of a game's observe stream, or the HTTP status the server refused it with. */
export type ObserveFetch =
    | { readonly ok: true; readonly answer: ObserveAnswer }
    | { readonly ok: false; readonly status: number };

/** How long an observe request may take, its body included, before it fails as a `TimeoutError`. */
export const OBSERVE_REQUEST_TIMEOUT_MS = 10_000;

/** A request's own signal: aborted with `signal`, or once its time runs out; `release` drops both. */
interface BoundedSignal {
    readonly signal: AbortSignal;
    readonly timedOut: () => boolean;
    readonly release: () => void;
}

function boundSignal(signal: AbortSignal, timeoutMs: number): BoundedSignal {
    const bounded = new AbortController();
    function abort(): void {
        bounded.abort(signal.reason);
    }
    const timer = setTimeout(() => bounded.abort(), timeoutMs);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) {
        abort();
    }
    return {
        release: (): void => {
            clearTimeout(timer);
            signal.removeEventListener("abort", abort);
        },
        signal: bounded.signal,
        timedOut: () => bounded.signal.aborted && !signal.aborted,
    };
}

async function requestObserve(url: string, signal: AbortSignal): Promise<ObserveFetch> {
    const response = await fetch(url, { signal });
    if (!response.ok) {
        return { ok: false, status: response.status };
    }
    return {
        answer: decodeObserveAnswer(new Uint8Array(await response.arrayBuffer())),
        ok: true,
    };
}

/**
 * Fetch the observe stream's records from cursor `from`; rejects on a network failure or a body that is no observe
 * answer, with a `TimeoutError` once `OBSERVE_REQUEST_TIMEOUT_MS` passes without the whole answer, and with an
 * `AbortError` once `signal` aborts. The signals are joined by hand: `AbortSignal.any` is newer than the supported
 * Safari.
 */
export async function fetchObserve(
    gameId: string,
    from: number,
    signal: AbortSignal,
): Promise<ObserveFetch> {
    const url = `/api/observe/${encodeURIComponent(gameId)}?from=${from}`;
    const bounded = boundSignal(signal, OBSERVE_REQUEST_TIMEOUT_MS);
    try {
        return await requestObserve(url, bounded.signal);
    } catch (error: unknown) {
        throw bounded.timedOut()
            ? new DOMException("The observe request timed out", "TimeoutError")
            : error;
    } finally {
        bounded.release();
    }
}

function abortError(): DOMException {
    return new DOMException("The replay load was cancelled", "AbortError");
}

/** Resolve after `delayMs` on the given timer, or reject with an `AbortError` once `signal` aborts, cancelling it. */
function wait(delayMs: number, retry: ReplayLoadRetry): Promise<void> {
    const { setTimer, signal } = retry;
    return new Promise((resolve, reject) => {
        if (signal.aborted) {
            reject(abortError());
            return;
        }
        const cancel = setTimer(delayMs, settle);
        function settle(): void {
            signal.removeEventListener("abort", abort);
            resolve();
        }
        function abort(): void {
            cancel();
            reject(abortError());
        }
        signal.addEventListener("abort", abort, { once: true });
    });
}

export interface ReplayLoadRetry {
    readonly signal: AbortSignal;
    readonly setTimer: (delayMs: number, callback: () => void) => CancelTimer;
    /** Called once, as the first 404 starts the waiting. */
    readonly onWaiting: () => void;
}

interface ReplayLoad {
    readonly load: LoadReplay;
    readonly gameId: string;
    readonly retry: ReplayLoadRetry;
}

function isNotFound(fetched: ReplayFetch): boolean {
    return !fetched.ok && fetched.status === HTTP_NOT_FOUND;
}

async function loadAfterEach(request: ReplayLoad, delays: readonly number[]): Promise<ReplayFetch> {
    const [delayMs, ...later] = delays;
    await wait(delayMs, request.retry);
    const fetched = await request.load(request.gameId, request.retry.signal);
    return isNotFound(fetched) && later.length > 0 ? loadAfterEach(request, later) : fetched;
}

/**
 * Load a replay, asking again after each of `REPLAY_NOT_FOUND_RETRY_MS` while the server answers 404, and settling
 * with the last answer; any other answer settles at once. Aborting `signal` cancels a waiting retry and rejects with
 * an `AbortError`.
 */
export async function loadReplayUntilFound(
    load: LoadReplay,
    gameId: string,
    retry: ReplayLoadRetry,
): Promise<ReplayFetch> {
    const fetched = await load(gameId, retry.signal);
    if (!isNotFound(fetched)) {
        return fetched;
    }
    retry.onWaiting();
    return loadAfterEach({ gameId, load, retry }, REPLAY_NOT_FOUND_RETRY_MS);
}
