import { type CancelTimer, type Clock } from "@/shared/clock";

/**
 * Where a load stands: under way, done, a failed try waiting for its next, or every try spent until the browser
 * comes back online.
 */
export type LoadStatus = "loading" | "ready" | "retrying" | "failed";

/** A load as its readers see it: where it stands, what it loaded once ready, and each change of its status. */
export interface RetryingLoad<Value> {
    readonly status: () => LoadStatus;
    /** What the load resolved to; null until it is ready. */
    readonly value: () => Value | null;
    /** Call `listener` with each new status; returns the call that stops it. */
    readonly subscribe: (listener: (status: LoadStatus) => void) => () => void;
    /** Stop trying: cancel a waiting retry, stop listening for the browser coming online, and drop a late result. */
    readonly stop: () => void;
}

export interface RetryingLoadDeps<Value> {
    /** One try; rejects on a failure worth trying again. */
    readonly load: () => Promise<Value>;
    readonly setTimer: Clock["setTimer"];
    /** Call `listener` each time the browser comes back online; returns the call that stops it. */
    readonly onOnline: (listener: () => void) => () => void;
    readonly reportFailure: (error: unknown) => void;
}

/** The wait before each retry of a failed load; once they are spent, only coming back online tries again. */
export const LOAD_RETRY_DELAYS_MS: readonly number[] = [1000, 2000, 4000, 8000, 16_000];

type Outcome<Value> =
    | { readonly ok: true; readonly value: Value }
    | { readonly ok: false; readonly error: unknown };

/** One load, from its first try to its first success. */
class Load<Value> implements RetryingLoad<Value> {
    private readonly deps: RetryingLoadDeps<Value>;
    private readonly listeners = new Set<(status: LoadStatus) => void>();
    private readonly stopOnline: () => void;
    private current: LoadStatus = "loading";
    private loaded: Value | null = null;
    private retries = 0;
    private inFlight = false;
    private stopped = false;
    private cancelRetry: CancelTimer | null = null;

    constructor(deps: RetryingLoadDeps<Value>) {
        this.deps = deps;
        this.stopOnline = deps.onOnline(() => this.retryNow());
        void this.attempt();
    }

    readonly status = (): LoadStatus => this.current;

    readonly value = (): Value | null => this.loaded;

    readonly subscribe = (listener: (status: LoadStatus) => void): (() => void) => {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    };

    readonly stop = (): void => {
        this.stopped = true;
        this.stopOnline();
        this.cancelRetry?.();
        this.cancelRetry = null;
        this.listeners.clear();
    };

    private setStatus(next: LoadStatus): void {
        if (next === this.current) {
            return;
        }
        this.current = next;
        for (const listener of this.listeners) {
            listener(next);
        }
    }

    private async attempt(): Promise<void> {
        this.inFlight = true;
        const outcome = await this.tryLoad();
        this.inFlight = false;
        if (this.stopped) {
            return;
        }
        if (outcome.ok) {
            this.settle(outcome.value);
            return;
        }
        this.deps.reportFailure(outcome.error);
        this.scheduleRetry();
    }

    private async tryLoad(): Promise<Outcome<Value>> {
        try {
            return { ok: true, value: await this.deps.load() };
        } catch (error: unknown) {
            return { error, ok: false };
        }
    }

    private settle(value: Value): void {
        this.loaded = value;
        this.stopOnline();
        this.setStatus("ready");
    }

    private scheduleRetry(): void {
        const delay = LOAD_RETRY_DELAYS_MS[this.retries];
        if (delay === undefined) {
            this.setStatus("failed");
            return;
        }
        this.retries += 1;
        this.cancelRetry = this.deps.setTimer(delay, () => {
            this.cancelRetry = null;
            void this.attempt();
        });
        this.setStatus("retrying");
    }

    /** Coming back online: try at once, in place of a waiting retry, unless a try runs or the load is done. */
    private retryNow(): void {
        if (this.inFlight || this.current === "ready" || this.stopped) {
            return;
        }
        this.cancelRetry?.();
        this.cancelRetry = null;
        void this.attempt();
    }
}

/**
 * Start a load that retries: a failure tries again after each of the backoff's waits, and coming back online tries
 * again at once, even after the waits are spent. One try runs at a time, and the load stops at its first success.
 */
export function startRetryingLoad<Value>(deps: RetryingLoadDeps<Value>): RetryingLoad<Value> {
    return new Load(deps);
}
