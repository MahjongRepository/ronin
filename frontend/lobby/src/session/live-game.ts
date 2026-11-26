import { apiGet, isRecord } from "@/api";

import { type GameStart, enterGame, readGameStart } from "./handoff";

const NOT_PLAYING = "not_playing";

/** Whether the user plays a game, and how a click taking them back into it went. */
export interface LiveGameReturn {
    playing: boolean;
    returnFailed: boolean;
    returning: boolean;
}

export interface LiveGameContext {
    readonly isDisposed: () => boolean;
    readonly render: () => void;
}

type LiveGameLookup =
    | { readonly kind: "playing"; readonly game: GameStart }
    | { readonly kind: "none" }
    | { readonly kind: "failed" };

export function createLiveGameReturn(): LiveGameReturn {
    return { playing: false, returnFailed: false, returning: false };
}

async function lookUpLiveGame(): Promise<LiveGameLookup> {
    const result = await apiGet("/api/game-session");
    if (!result.ok) {
        return result.error === NOT_PLAYING ? { kind: "none" } : { kind: "failed" };
    }
    const game = isRecord(result.data) ? readGameStart(result.data) : null;
    if (game === null) {
        console.error("game session not read", "invalid answer");
        return { kind: "failed" };
    }
    return { game, kind: "playing" };
}

/** Find whether the user plays a game, of any kind, so the page offers the way back into it. */
export async function checkLiveGame(live: LiveGameReturn, context: LiveGameContext): Promise<void> {
    const lookup = await lookUpLiveGame();
    if (context.isDisposed()) {
        return;
    }
    live.playing = lookup.kind === "playing";
    context.render();
}

/** Leave for the game, or report that its claim could not be stored, since the game page would not find it. */
function enterReturnedGame(game: GameStart): boolean {
    try {
        enterGame(game);
        return true;
    } catch (error: unknown) {
        console.error("game session not stored", error);
        return false;
    }
}

function finishReturn(
    live: LiveGameReturn,
    lookup: LiveGameLookup,
    context: LiveGameContext,
): void {
    if (lookup.kind === "playing" && enterReturnedGame(lookup.game)) {
        return;
    }
    live.returning = false;
    live.playing = lookup.kind !== "none";
    live.returnFailed = lookup.kind !== "none";
    context.render();
}

/**
 * Enter the user's live game with a fresh handoff, taking the seat over from any tab that holds it; a game that
 * ended meanwhile drops the offer, and a lookup that failed can be retried.
 */
export async function returnToGame(live: LiveGameReturn, context: LiveGameContext): Promise<void> {
    if (live.returning) {
        return;
    }
    live.returning = true;
    live.returnFailed = false;
    context.render();
    const lookup = await lookUpLiveGame();
    if (!context.isDisposed()) {
        finishReturn(live, lookup, context);
    }
}
