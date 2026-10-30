import { describe, expect, test } from "vitest";

import { ManualClock } from "#tests/fixtures/clock";
import {
    type LoadReplay,
    type ReplayFetch,
    type ReplayLoadRetry,
    isAbortError,
    loadReplayUntilFound,
} from "@/shared/api";

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
const FOUND: ReplayFetch = { ok: true, text: "replay" };

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
