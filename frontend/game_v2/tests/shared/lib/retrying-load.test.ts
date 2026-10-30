import { describe, expect, it, vi } from "vitest";

import { ManualClock } from "#tests/fixtures/clock";
import {
    LOAD_RETRY_DELAYS_MS,
    type LoadStatus,
    type RetryingLoad,
    startRetryingLoad,
} from "@/shared/lib";

const LOADED = "loaded";

interface Harness {
    readonly clock: ManualClock;
    readonly load: ReturnType<typeof vi.fn<() => Promise<string>>>;
    readonly goOnline: () => void;
    readonly started: RetryingLoad<string>;
    readonly statuses: LoadStatus[];
}

/** Start a load whose every try answers `answer` until a test changes it. */
function startLoad(answer: () => Promise<string>): Harness {
    const clock = new ManualClock();
    const load = vi.fn(answer);
    const onlineListeners = new Set<() => void>();
    const started = startRetryingLoad({
        load,
        onOnline: (listener) => {
            onlineListeners.add(listener);
            return () => onlineListeners.delete(listener);
        },
        reportFailure: () => {},
        setTimer: clock.setTimer,
    });
    const statuses: LoadStatus[] = [];
    started.subscribe((status) => statuses.push(status));
    function goOnline(): void {
        for (const listener of onlineListeners) {
            listener();
        }
    }
    return { clock, goOnline, load, started, statuses };
}

function offline(): Promise<string> {
    return Promise.reject(new TypeError("Failed to fetch"));
}

/** Hold every try from now on until the returned call lands them all with its value. */
function holdTries(load: Harness["load"]): (value: string) => void {
    const held: ((value: string) => void)[] = [];
    load.mockImplementation(
        () =>
            new Promise((resolve) => {
                held.push(resolve);
            }),
    );
    return (value) => {
        for (const resolve of held) {
            resolve(value);
        }
    };
}

/** Fire each retry the backoff arms from the `index`th on, letting the try it starts fail first. */
async function spendRetries(harness: Harness, index = 0, at = 0): Promise<void> {
    const delay = LOAD_RETRY_DELAYS_MS[index];
    if (delay === undefined) {
        return;
    }
    const { clock, load } = harness;
    await vi.waitFor(() => expect(clock.timers).toHaveLength(index + 1));
    clock.advanceTo(at + delay);
    await vi.waitFor(() => expect(load).toHaveBeenCalledTimes(index + 2));
    await spendRetries(harness, index + 1, at + delay);
}

describe("startRetryingLoad", () => {
    it("holds what it loaded once ready, with no retry armed", async () => {
        const { clock, started } = startLoad(() => Promise.resolve(LOADED));
        expect([started.status(), started.value()]).toEqual(["loading", null]);

        await vi.waitFor(() => expect(started.status()).toBe("ready"));

        expect(started.value()).toBe(LOADED);
        expect(clock.timers).toHaveLength(0);
    });

    it("retries a failed load after the backoff's first wait and is ready once a retry loads", async () => {
        const { clock, load, started, statuses } = startLoad(offline);
        await vi.waitFor(() => expect(started.status()).toBe("retrying"));
        load.mockImplementation(() => Promise.resolve(LOADED));

        clock.advanceTo(LOAD_RETRY_DELAYS_MS[0] - 1);
        expect(load).toHaveBeenCalledOnce();
        clock.advanceTo(LOAD_RETRY_DELAYS_MS[0]);

        await vi.waitFor(() => expect(started.status()).toBe("ready"));
        expect(load).toHaveBeenCalledTimes(2);
        expect(statuses).toEqual(["retrying", "ready"]);
    });

    it("gives up once every retry failed, then tries once more when the browser comes back online", async () => {
        const harness = startLoad(offline);
        const { clock, goOnline, load, started, statuses } = harness;

        await spendRetries(harness);
        await vi.waitFor(() => expect(started.status()).toBe("failed"));
        expect(clock.timers.filter((timer) => !timer.cancelled)).toHaveLength(0);
        load.mockImplementation(() => Promise.resolve(LOADED));
        goOnline();

        await vi.waitFor(() => expect(started.status()).toBe("ready"));
        expect(load).toHaveBeenCalledTimes(LOAD_RETRY_DELAYS_MS.length + 2);
        expect(statuses).toEqual(["retrying", "failed", "ready"]);
    });

    it("tries at once when the browser comes back online during a wait, cancelling the wait's retry", async () => {
        const { clock, goOnline, load, started } = startLoad(offline);
        await vi.waitFor(() => expect(started.status()).toBe("retrying"));
        load.mockImplementation(() => Promise.resolve(LOADED));

        goOnline();
        goOnline();
        await vi.waitFor(() => expect(started.status()).toBe("ready"));
        clock.advanceTo(LOAD_RETRY_DELAYS_MS[0]);

        expect(load).toHaveBeenCalledTimes(2);
    });

    it("once stopped, cancels its waiting retry, ignores coming online and drops a try that lands late", async () => {
        const { clock, goOnline, load, started, statuses } = startLoad(offline);
        await vi.waitFor(() => expect(started.status()).toBe("retrying"));
        const land = holdTries(load);
        goOnline();

        started.stop();
        land(LOADED);
        goOnline();
        clock.advanceTo(LOAD_RETRY_DELAYS_MS[0]);
        await Promise.resolve();

        expect([load.mock.calls.length, started.status(), started.value(), statuses]).toEqual([
            2,
            "retrying",
            null,
            ["retrying"],
        ]);
    });
});
