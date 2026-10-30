import { describe, expect, it, vi } from "vitest";

import { ManualClock } from "#tests/fixtures/clock";
import { loadTileSprite } from "@/entities/tile";

const SPRITE = "<svg><symbol id='tile-1m'/></svg>";

function startSprite(inject: (sprite: string) => void): ReturnType<typeof loadTileSprite> {
    return loadTileSprite({
        fetchSprite: () => Promise.resolve(SPRITE),
        inject,
        onOnline: () => () => {},
        reportFailure: () => {},
        setTimer: new ManualClock().setTimer,
    });
}

describe("loadTileSprite", () => {
    it("injects the fetched sprite and is ready", async () => {
        const inject = vi.fn<(sprite: string) => void>();
        const sprite = startSprite(inject);

        await vi.waitFor(() => expect(sprite.status()).toBe("ready"));

        expect(inject).toHaveBeenCalledExactlyOnceWith(SPRITE);
    });

    it("treats sprite markup the injector refuses as a failed load", async () => {
        const sprite = startSprite(() => {
            throw new Error("the tile sprite holds no tile symbol");
        });

        await vi.waitFor(() => expect(sprite.status()).toBe("retrying"));
    });
});
