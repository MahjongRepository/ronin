import { type LoadedReplay } from "@/entities/replay/model/read-replay";
import { type ReplayCursor } from "@/entities/replay/model/replay-cursor";
import { CALLOUT_MS } from "@/entities/table";

/** The stop whose calls the board shows, since when (logical time) and until when. */
export interface ShownReplayCall {
    readonly stop: number;
    readonly at: number;
    readonly until: number;
}

/** A move of the reader's: from where (none on opening the replay), to where, at what logical time. */
export interface CallMove {
    readonly from: ReplayCursor | null;
    readonly to: ReplayCursor;
    readonly at: number;
}

/**
 * The stop whose calls show once the reader moves from `from` to `to` at logical time `at`: a stop's own calls on
 * arriving at it, kept as its pages turn; else the calls still in their time that the reader moved on from within
 * their round, so a call fades on its own clock rather than at the next move. None after stepping back past a call,
 * into another round, or once its time is up.
 */
export function shownReplayCall(
    source: Pick<LoadedReplay, "calls" | "navigation">,
    shown: ShownReplayCall | null,
    { at, from, to }: CallMove,
): ShownReplayCall | null {
    if (from?.stop === to.stop) {
        return shown;
    }
    const { stops } = source.navigation;
    const target = stops[to.stop];
    if ((source.calls[target.stateIndex]?.length ?? 0) > 0) {
        return { at, stop: to.stop, until: at + CALLOUT_MS };
    }
    const carried =
        shown !== null &&
        at < shown.until &&
        to.stop > shown.stop &&
        stops[shown.stop].round === target.round;
    return carried ? shown : null;
}
