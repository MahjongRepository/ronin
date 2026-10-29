import { type CancelTimer, type Clock } from "@/shared/clock";

/**
 * Where the tile sprite's load stands: under way, its faces shown, a failed load waiting for its next try, or every
 * try spent until the browser comes back online.
 */
export type TileSpriteStatus = "loading" | "ready" | "retrying" | "failed";

/** The tile sprite's load as its readers see it: the live game's board says when the faces are missing. */
export interface TileSprite {
    readonly status: () => TileSpriteStatus;
    /** Call `listener` with each new status; returns the call that stops it. */
    readonly subscribe: (listener: (status: TileSpriteStatus) => void) => () => void;
}

export interface TileSpriteDeps {
    /** The sprite's markup; rejects on a failed request or an answer that is not OK. */
    readonly fetchSprite: () => Promise<string>;
    /** Put the markup's symbols in the document; throws on markup holding none. */
    readonly inject: (sprite: string) => void;
    readonly setTimer: Clock["setTimer"];
    /** Call `listener` each time the browser comes back online; returns the call that stops it. */
    readonly onOnline: (listener: () => void) => () => void;
    readonly reportFailure: (error: unknown) => void;
}

/** The wait before each retry of a failed load; once they are spent, only coming back online tries again. */
export const TILE_SPRITE_RETRY_DELAYS_MS: readonly number[] = [1000, 2000, 4000, 8000, 16_000];

/** One load of the sprite, from its first request to its first success. */
class TileSpriteLoad implements TileSprite {
    private readonly deps: TileSpriteDeps;
    private readonly listeners = new Set<(status: TileSpriteStatus) => void>();
    private readonly stopOnline: () => void;
    private current: TileSpriteStatus = "loading";
    private retries = 0;
    private inFlight = false;
    private cancelRetry: CancelTimer | null = null;

    constructor(deps: TileSpriteDeps) {
        this.deps = deps;
        this.stopOnline = deps.onOnline(() => this.retryNow());
        void this.attempt();
    }

    readonly status = (): TileSpriteStatus => this.current;

    readonly subscribe = (listener: (status: TileSpriteStatus) => void): (() => void) => {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    };

    private setStatus(next: TileSpriteStatus): void {
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
        try {
            this.deps.inject(await this.deps.fetchSprite());
        } catch (error: unknown) {
            this.inFlight = false;
            this.deps.reportFailure(error);
            this.scheduleRetry();
            return;
        }
        this.inFlight = false;
        this.stopOnline();
        this.setStatus("ready");
    }

    private scheduleRetry(): void {
        const delay = TILE_SPRITE_RETRY_DELAYS_MS[this.retries];
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

    /** Coming back online: try at once, in place of a waiting retry, unless a request runs or the load is done. */
    private retryNow(): void {
        if (this.inFlight || this.current === "ready") {
            return;
        }
        this.cancelRetry?.();
        this.cancelRetry = null;
        void this.attempt();
    }
}

/**
 * Start loading the tile sprite: fetched as an asset rather than imported as a module, so a failed request can be
 * tried again. A failure retries after each of the backoff's waits, and coming back online tries again at once,
 * even after the waits are spent. One request runs at a time, and the load stops at the first success.
 */
export function loadTileSprite(deps: TileSpriteDeps): TileSprite {
    return new TileSpriteLoad(deps);
}
