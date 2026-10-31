import { type NavigationIndex, type ReplayRound } from "./navigation-index";

/** Where a replay stands: a stop, and the page of the result it shows (a double ron's winner). */
export interface ReplayCursor {
    readonly stop: number;
    readonly page: number;
}

/** A position as the page's address names it: the recorded deal and the stop within it, both from 0 at its deal. */
export interface RoundPosition {
    readonly round: number;
    readonly step: number;
}

function lastPage(nav: NavigationIndex, stop: number): number {
    return nav.stops[stop].pages - 1;
}

/** The cursor at a round's deal, or null for a round the replay does not hold. */
export function roundStartCursor(nav: NavigationIndex, round: number): ReplayCursor | null {
    const start = nav.rounds.at(round);
    return round < 0 || start === undefined ? null : { page: 0, stop: start.firstStop };
}

/** The cursor at a round's result, at its first page; null for a round the replay does not hold or holds no result of. */
export function roundResultCursor(nav: NavigationIndex, round: number): ReplayCursor | null {
    const stop = round < 0 ? null : (nav.rounds.at(round)?.resultStop ?? null);
    return stop === null ? null : { page: 0, stop };
}

/** The replay's opening: the first deal; null for a replay with none. */
export function firstCursor(nav: NavigationIndex): ReplayCursor | null {
    return roundStartCursor(nav, 0);
}

/** The replay's last stop with every page of its result shown. */
export function lastCursor(nav: NavigationIndex): ReplayCursor | null {
    const stop = nav.stops.length - 1;
    return stop < 0 ? null : { page: lastPage(nav, stop), stop };
}

/** One move on: the result's next page, else the next stop's first; null at the end. */
export function nextCursor(nav: NavigationIndex, cursor: ReplayCursor): ReplayCursor | null {
    if (cursor.page < lastPage(nav, cursor.stop)) {
        return { page: cursor.page + 1, stop: cursor.stop };
    }
    const stop = cursor.stop + 1;
    return stop < nav.stops.length ? { page: 0, stop } : null;
}

/** One move back: the result's previous page, else the previous stop at its last page; null at the first deal. */
export function prevCursor(nav: NavigationIndex, cursor: ReplayCursor): ReplayCursor | null {
    if (cursor.page > 0) {
        return { page: cursor.page - 1, stop: cursor.stop };
    }
    const stop = cursor.stop - 1;
    return stop >= 0 ? { page: lastPage(nav, stop), stop } : null;
}

/** The round a cursor stands in. */
export function cursorRound(nav: NavigationIndex, cursor: ReplayCursor): ReplayRound {
    return nav.rounds[nav.stops[cursor.stop].round];
}

/** The next round's deal; null in the last round. */
export function nextRoundCursor(nav: NavigationIndex, cursor: ReplayCursor): ReplayCursor | null {
    return roundStartCursor(nav, nav.stops[cursor.stop].round + 1);
}

/** Back to this round's deal, or from its deal to the previous round's; null at the first deal. */
export function prevRoundCursor(nav: NavigationIndex, cursor: ReplayCursor): ReplayCursor | null {
    const { round } = nav.stops[cursor.stop];
    const atDeal = cursor.stop === nav.rounds[round].firstStop && cursor.page === 0;
    return roundStartCursor(nav, atDeal ? round - 1 : round);
}

/** A cursor's place in its round, as the address names it: the round, and its stop counted from 0 at the deal. */
export function roundPosition(nav: NavigationIndex, cursor: ReplayCursor): RoundPosition {
    const { round } = nav.stops[cursor.stop];
    return { round, step: cursor.stop - nav.rounds[round].firstStop };
}

/** The cursor at a round's step, at its first page; null for a position the replay does not hold. */
export function positionCursor(nav: NavigationIndex, position: RoundPosition): ReplayCursor | null {
    const round = nav.rounds.at(position.round);
    if (position.round < 0 || round === undefined) {
        return null;
    }
    if (position.step < 0 || position.step >= round.stopCount) {
        return null;
    }
    return { page: 0, stop: round.firstStop + position.step };
}
