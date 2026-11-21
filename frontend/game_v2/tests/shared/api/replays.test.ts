import { encode } from "@msgpack/msgpack";
import { afterEach, describe, expect, test, vi } from "vitest";

import { ManualClock } from "#tests/fixtures/clock";
import {
    type LoadReplay,
    OBSERVE_REQUEST_TIMEOUT_MS,
    type ReplayFetch,
    type ReplayLoadRetry,
    fetchObserve,
    fetchReplay,
    isAbortError,
    loadReplayUntilFound,
} from "@/shared/api";
import { REPLAY_VERSION } from "@/shared/protocol";

describe("isAbortError", () => {
    test("true for DOMException with name AbortError", () => {
        expect(isAbortError(new DOMException("aborted", "AbortError"))).toBe(true);
    });

    test("false for DOMException with different name", () => {
        expect(isAbortError(new DOMException("timeout", "TimeoutError"))).toBe(false);
    });

    test("false for regular Error", () => {
        expect(isAbortError(new Error("aborted"))).toBe(false);
    });

    test("false for non-error values", () => {
        expect(isAbortError(null)).toBe(false);
        expect(isAbortError("AbortError")).toBe(false);
    });
});

describe("fetchReplay", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    test("asks for the replay at the URL of the replay version the client reads", async () => {
        const fetched = vi.fn(() => Promise.resolve(new Response(new Uint8Array([7]))));
        vi.stubGlobal("fetch", fetched);
        const { signal } = new AbortController();

        await expect(fetchReplay("g 1", signal)).resolves.toEqual({
            content: new Uint8Array([7]),
            ok: true,
        });
        expect(fetched).toHaveBeenCalledWith(
            `/api/replays/g%201?v=${encodeURIComponent(REPLAY_VERSION)}`,
            { signal },
        );
    });
});

/** A fetch whose headers arrive at once and whose body ends only as its request's signal aborts, with its reason. */
function bodyUntilAborted(_url: string, init?: RequestInit): Promise<Response> {
    const { signal } = init ?? {};
    const body = new ReadableStream({
        start(controller): void {
            signal?.addEventListener("abort", () => controller.error(signal.reason), {
                once: true,
            });
        },
    });
    return Promise.resolve(new Response(body));
}

/** The error an observe request whose body never ends rejects with, once `end` ran on its caller's controller. */
async function unfinishedObserveError(
    end: (caller: AbortController) => Promise<void>,
): Promise<unknown> {
    vi.stubGlobal("fetch", vi.fn(bodyUntilAborted));
    const caller = new AbortController();
    const settled = fetchObserve("g", 3, caller.signal).then(
        () => null,
        (error: unknown) => error,
    );
    await end(caller);
    return settled;
}

describe("fetchObserve", () => {
    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    test("fails a body still unanswered past its time limit as a timeout, and one its caller aborts as aborted", async () => {
        vi.useFakeTimers();

        const timedOut = await unfinishedObserveError(async () => {
            await vi.advanceTimersByTimeAsync(OBSERVE_REQUEST_TIMEOUT_MS);
        });
        const aborted = await unfinishedObserveError(async (caller) => {
            await vi.advanceTimersByTimeAsync(OBSERVE_REQUEST_TIMEOUT_MS - 1);
            caller.abort();
        });

        expect([timedOut, aborted]).toEqual([
            expect.objectContaining({ name: "TimeoutError" }),
            expect.objectContaining({ name: "AbortError" }),
        ]);
        expect(vi.getTimerCount()).toBe(0);
    });

    test("asks the stream from the cursor given and decodes the server's MessagePack answer, its records as bytes", async () => {
        const body = encode({
            available_in_ms: 0,
            ended: false,
            game_type: "hanchan",
            next: 52,
            players: ["East", "South", "West", "North"],
            records: new Uint8Array([129, 1, 2]),
            started_at: 1_790_000_000_123,
        });
        const fetched = vi.fn(() => Promise.resolve(new Response(body)));
        vi.stubGlobal("fetch", fetched);

        await expect(fetchObserve("g 1", 37, new AbortController().signal)).resolves.toEqual({
            answer: {
                availableInMs: 0,
                ended: false,
                gameType: "hanchan",
                next: 52,
                players: ["East", "South", "West", "North"],
                records: new Uint8Array([129, 1, 2]),
                startedAt: 1_790_000_000_123,
            },
            ok: true,
        });
        expect(fetched).toHaveBeenCalledWith("/api/observe/g%201?from=37", expect.anything());
    });
});

interface ScriptedLoad {
    readonly load: LoadReplay;
    readonly calls: () => number;
}

/** A loader answering each call with the next of `answers`, the last repeated. */
function scriptedLoad(answers: readonly ReplayFetch[]): ScriptedLoad {
    let calls = 0;
    return {
        calls: () => calls,
        load: () => {
            const answer = answers[Math.min(calls, answers.length - 1)];
            calls += 1;
            return Promise.resolve(answer);
        },
    };
}

const NOT_FOUND: ReplayFetch = { ok: false, status: 404 };
const FOUND: ReplayFetch = { content: new Uint8Array([1, 2, 3]), ok: true };

async function settle(turns = 5): Promise<void> {
    if (turns > 0) {
        await Promise.resolve();
        await settle(turns - 1);
    }
}

/** Move the clock to each time in turn, letting the load go on after each, and read `probe` there. */
async function readAt<Value>(
    clock: ManualClock,
    times: readonly number[],
    probe: () => Value,
): Promise<Value[]> {
    const [at, ...later] = times;
    if (at === undefined) {
        return [];
    }
    clock.advanceTo(at);
    await settle();
    return [probe(), ...(await readAt(clock, later, probe))];
}

function retryOn(clock: ManualClock, onWaiting = (): void => {}): ReplayLoadRetry {
    return { onWaiting, setTimer: clock.setTimer, signal: new AbortController().signal };
}

describe("loadReplayUntilFound", () => {
    test("asks again after 500, 1000 and 2000 ms while the replay is not found, then settles on it", async () => {
        const clock = new ManualClock();
        const scripted = scriptedLoad([NOT_FOUND, NOT_FOUND, NOT_FOUND, FOUND]);
        let waiting = 0;
        const loading = loadReplayUntilFound(
            scripted.load,
            "g1",
            retryOn(clock, () => {
                waiting += 1;
            }),
        );

        const calls = await readAt(clock, [0, 499, 500, 1499, 1500, 3499, 3500], scripted.calls);

        expect(calls).toEqual([1, 1, 2, 2, 3, 3, 4]);
        expect(await loading).toEqual(FOUND);
        expect(waiting).toBe(1);
    });

    test("settles on 404 once its retries are spent, and at once on any other answer", async () => {
        const clock = new ManualClock();
        const missing = loadReplayUntilFound(scriptedLoad([NOT_FOUND]).load, "g1", retryOn(clock));
        await readAt(clock, [0, 500, 1500, 3500], () => null);
        const refused = scriptedLoad([{ ok: false, status: 500 }]);

        expect(await missing).toEqual(NOT_FOUND);
        expect(await loadReplayUntilFound(refused.load, "g1", retryOn(clock))).toEqual({
            ok: false,
            status: 500,
        });
    });

    test("cancels a waiting retry when aborted, asking nothing more", async () => {
        const clock = new ManualClock();
        const abort = new AbortController();
        const scripted = scriptedLoad([NOT_FOUND]);
        const loading = loadReplayUntilFound(scripted.load, "g1", {
            onWaiting: () => {},
            setTimer: clock.setTimer,
            signal: abort.signal,
        });
        await settle();

        abort.abort();
        clock.advanceTo(10_000);

        await expect(loading).rejects.toSatisfy(isAbortError);
        expect(scripted.calls()).toBe(1);
        expect(clock.lastTimer().cancelled).toBe(true);
    });
});
