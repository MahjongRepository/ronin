import { type Clock } from "@/shared/clock";
import { type LoadStatus, type RetryingLoad, startRetryingLoad } from "@/shared/lib";

/**
 * Where the tile sprite's load stands: under way, its faces shown, a failed load waiting for its next try, or every
 * try spent until the browser comes back online.
 */
export type TileSpriteStatus = LoadStatus;

/** The tile sprite's load as its readers see it: the live game's board says when the faces are missing. */
export type TileSprite = Pick<RetryingLoad<void>, "status" | "subscribe">;

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

/**
 * Start loading the tile sprite: fetched as an asset rather than imported as a module, so a failed request can be
 * tried again, with the retries of `startRetryingLoad`; markup the injector refuses counts as a failed try.
 */
export function loadTileSprite({ fetchSprite, inject, ...deps }: TileSpriteDeps): TileSprite {
    return startRetryingLoad({
        ...deps,
        load: async () => {
            inject(await fetchSprite());
        },
    });
}
