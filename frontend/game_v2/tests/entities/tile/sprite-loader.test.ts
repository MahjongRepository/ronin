import { describe, expect, it, vi } from "vitest";

import { ManualClock } from "#tests/fixtures/clock";
import {
    TILE_SPRITE_RETRY_DELAYS_MS,
    type TileSprite,
    type TileSpriteStatus,
    loadTileSprite,
} from "@/entities/tile";

const SPRITE = "<svg><symbol id='tile-1m'/></svg>";

interface Harness {
    readonly clock: ManualClock;
    readonly fetchSprite: ReturnType<typeof vi.fn<() => Promise<string>>>;
    readonly inject: ReturnType<typeof vi.fn<(sprite: string) => void>>;
    readonly goOnline: () => void;
    readonly sprite: TileSprite;
    readonly statuses: TileSpriteStatus[];
}

/** Load the sprite with every fetch answering `answer` until a test changes it. */
function startLoad(answer: () => Promise<string>): Harness {
    const clock = new ManualClock();
    const fetchSprite = vi.fn(answer);
    const inject = vi.fn<(sprite: string) => void>();
    const onlineListeners = new Set<() => void>();
    const sprite = loadTileSprite({
        fetchSprite,
        inject,
        onOnline: (listener) => {
            onlineListeners.add(listener);
            return () => onlineListeners.delete(listener);
        },
        reportFailure: () => {},
        setTimer: clock.setTimer,
    });
    const statuses: TileSpriteStatus[] = [];
    sprite.subscribe((status) => statuses.push(status));
    function goOnline(): void {
        for (const listener of onlineListeners) {
            listener();
        }
    }
    return { clock, fetchSprite, goOnline, inject, sprite, statuses };
}

function offline(): Promise<string> {
    return Promise.reject(new TypeError("Failed to fetch"));
}

/** Fire each retry the backoff arms from the `index`th on, letting the request it starts fail first. */
async function spendRetries(harness: Harness, index = 0, at = 0): Promise<void> {
    const delay = TILE_SPRITE_RETRY_DELAYS_MS[index];
    if (delay === undefined) {
        return;
    }
    const { clock, fetchSprite } = harness;
    await vi.waitFor(() => expect(clock.timers).toHaveLength(index + 1));
    clock.advanceTo(at + delay);
    await vi.waitFor(() => expect(fetchSprite).toHaveBeenCalledTimes(index + 2));
    await spendRetries(harness, index + 1, at + delay);
}

describe("loadTileSprite", () => {
    it("injects the fetched sprite and is ready, with no retry armed", async () => {
        const { clock, inject, sprite } = startLoad(() => Promise.resolve(SPRITE));
        expect(sprite.status()).toBe("loading");

        await vi.waitFor(() => expect(sprite.status()).toBe("ready"));

        expect(inject).toHaveBeenCalledExactlyOnceWith(SPRITE);
        expect(clock.timers).toHaveLength(0);
    });

    it("retries a failed load after the backoff's first wait and is ready once a retry loads", async () => {
        const harness = startLoad(offline);
        const { clock, fetchSprite, sprite, statuses } = harness;
        await vi.waitFor(() => expect(sprite.status()).toBe("retrying"));
        fetchSprite.mockImplementation(() => Promise.resolve(SPRITE));

        clock.advanceTo(TILE_SPRITE_RETRY_DELAYS_MS[0] - 1);
        expect(fetchSprite).toHaveBeenCalledOnce();
        clock.advanceTo(TILE_SPRITE_RETRY_DELAYS_MS[0]);

        await vi.waitFor(() => expect(sprite.status()).toBe("ready"));
        expect(fetchSprite).toHaveBeenCalledTimes(2);
        expect(statuses).toEqual(["retrying", "ready"]);
    });

    it("treats sprite markup the injector refuses as a failed load", async () => {
        const { inject, sprite } = startLoad(() => Promise.resolve("<html>Bad gateway</html>"));
        inject.mockImplementation(() => {
            throw new Error("the tile sprite holds no tile symbol");
        });

        await vi.waitFor(() => expect(sprite.status()).toBe("retrying"));
    });

    it("gives up once every retry failed, then tries once more when the browser comes back online", async () => {
        const harness = startLoad(offline);
        const { clock, fetchSprite, goOnline, sprite, statuses } = harness;

        await spendRetries(harness);
        await vi.waitFor(() => expect(sprite.status()).toBe("failed"));
        expect(clock.timers.filter((timer) => !timer.cancelled)).toHaveLength(0);
        fetchSprite.mockImplementation(() => Promise.resolve(SPRITE));
        goOnline();

        await vi.waitFor(() => expect(sprite.status()).toBe("ready"));
        expect(fetchSprite).toHaveBeenCalledTimes(TILE_SPRITE_RETRY_DELAYS_MS.length + 2);
        expect(statuses).toEqual(["retrying", "failed", "ready"]);
    });

    it("tries at once when the browser comes back online during a wait, cancelling the wait's retry", async () => {
        const { clock, fetchSprite, goOnline, sprite } = startLoad(offline);
        await vi.waitFor(() => expect(sprite.status()).toBe("retrying"));
        fetchSprite.mockImplementation(() => Promise.resolve(SPRITE));

        goOnline();
        goOnline();
        await vi.waitFor(() => expect(sprite.status()).toBe("ready"));
        clock.advanceTo(TILE_SPRITE_RETRY_DELAYS_MS[0]);

        expect(fetchSprite).toHaveBeenCalledTimes(2);
    });
});
