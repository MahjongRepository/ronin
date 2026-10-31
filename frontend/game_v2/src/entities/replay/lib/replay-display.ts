import { type StepEvent } from "@/entities/replay/model/action-steps";
import { type NavigationIndex } from "@/entities/replay/model/navigation-index";
import {
    type ReplayCursor,
    cursorRound,
    firstCursor,
    lastCursor,
    nextCursor,
    nextRoundCursor,
    prevCursor,
    prevRoundCursor,
    roundPosition,
    roundStartCursor,
} from "@/entities/replay/model/replay-cursor";
import {
    type BoardCallouts,
    type BoardPerspective,
    type Call,
    type ReplayLineError,
    type TableState,
    boardCallouts,
    formatRoundName,
    honbaName,
    roundName,
    roundResultSummary,
} from "@/entities/table";

import { narrateStop } from "./replay-narration";

/** A replay that is not the whole game: a short label, and why. */
export interface ReplayIncompleteness {
    readonly label: string;
    readonly detail: string;
}

/**
 * A replay as its page reads it: the timeline's step events, and its tables with the calls each state shows (index by
 * index), its navigation, and where it broke off.
 */
export interface ReplaySource {
    readonly events: readonly StepEvent[];
    readonly tables: readonly TableState[];
    readonly calls: readonly (readonly Call[])[];
    readonly navigation: NavigationIndex;
    readonly damage: ReplayLineError | null;
}

/** Where each move control goes from the cursor: null where it cannot move. */
export interface ReplayMoves {
    readonly first: ReplayCursor | null;
    readonly prevRound: ReplayCursor | null;
    readonly prev: ReplayCursor | null;
    readonly next: ReplayCursor | null;
    readonly nextRound: ReplayCursor | null;
    readonly last: ReplayCursor | null;
}

/** A round of the round list: its name, its result in a line, and its deal to jump to. */
export interface ReplayRoundRow {
    readonly name: string;
    readonly summary: string;
    readonly current: boolean;
    readonly start: ReplayCursor;
}

/** What a replay page shows at a cursor beside the board: where it stands, what happened, where it can go. */
export interface ReplayDisplay {
    readonly table: TableState;
    /** The calls the stop's own move made, by their seats from the perspective's; null for a move that made none. */
    readonly callouts: BoardCallouts | null;
    /** The round's whole name, its honba included: "East 2, 1 honba". */
    readonly roundName: string;
    /** The round's name alone and its honba apart, which a narrow column leaves to the board: "East 2", "1 honba". */
    readonly roundTitle: string;
    readonly honbaLabel: string | null;
    /** The stop within its round, from 1 at the deal: "Step 3 of 42". */
    readonly step: { readonly index: number; readonly count: number };
    readonly narration: string;
    readonly moves: ReplayMoves;
    readonly rounds: readonly ReplayRoundRow[];
    /** Why the replay is not the whole game, shown on every stop; null for a whole game read in full. */
    readonly incomplete: ReplayIncompleteness | null;
    /** Said over the board at the last stop of a replay that is not the whole game. */
    readonly endNotice: string | null;
}

/** Why a replay is not the whole game: a line it stopped at, or a recording that ends before the game does. */
function incompleteness(source: ReplaySource): ReplayIncompleteness | null {
    if (source.damage !== null) {
        return {
            detail: `Line ${source.damage.lineNumber} could not be read, so the replay stops before it.`,
            label: "Damaged",
        };
    }
    if (source.navigation.complete) {
        return null;
    }
    return { detail: "The recording stops before the game's end.", label: "Incomplete" };
}

function endNotice(source: ReplaySource, cursor: ReplayCursor): string | null {
    if (incompleteness(source) === null || cursor.stop !== source.navigation.stops.length - 1) {
        return null;
    }
    return source.damage === null
        ? "The recording ends here, before the game's end"
        : `The replay stops here: line ${source.damage.lineNumber} could not be read`;
}

/** Where each move control goes from the cursor. */
export function replayMoves(nav: NavigationIndex, cursor: ReplayCursor): ReplayMoves {
    const atFirst = cursor.stop === 0 && cursor.page === 0;
    const last = lastCursor(nav);
    const atLast = last !== null && last.stop === cursor.stop && last.page === cursor.page;
    return {
        first: atFirst ? null : firstCursor(nav),
        last: atLast ? null : last,
        next: nextCursor(nav, cursor),
        nextRound: nextRoundCursor(nav, cursor),
        prev: prevCursor(nav, cursor),
        prevRound: prevRoundCursor(nav, cursor),
    };
}

function roundRows(nav: NavigationIndex, current: number): ReplayRoundRow[] {
    return nav.rounds.flatMap((round, index) => {
        const start = roundStartCursor(nav, index);
        return start === null
            ? []
            : [
                  {
                      current: index === current,
                      name: formatRoundName(round.wind, round.roundInWind, round.honba),
                      start,
                      summary: roundResultSummary(round.result, round.endTable.players),
                  },
              ];
    });
}

/** The calls a stop shows, keyed by the stop, so arriving on it plays them afresh and turning its pages does not. */
function stopCallouts(
    calls: readonly Call[],
    stop: number,
    perspective: BoardPerspective,
): BoardCallouts | null {
    if (calls.length === 0) {
        return null;
    }
    return { items: boardCallouts(calls, perspective.bottomSeat), key: `stop-${stop}` };
}

/** What the page shows at `cursor` from `perspective`: the table, the round and step, the narration and the moves. */
export function replayDisplay(
    source: ReplaySource,
    cursor: ReplayCursor,
    perspective: BoardPerspective,
): ReplayDisplay {
    const nav = source.navigation;
    const stop = nav.stops[cursor.stop];
    const round = cursorRound(nav, cursor);
    const position = roundPosition(nav, cursor);
    return {
        callouts: stopCallouts(source.calls[stop.stateIndex] ?? [], cursor.stop, perspective),
        endNotice: endNotice(source, cursor),
        honbaLabel: honbaName(round.honba),
        incomplete: incompleteness(source),
        moves: replayMoves(nav, cursor),
        narration: narrateStop(source, stop, perspective),
        roundName: formatRoundName(round.wind, round.roundInWind, round.honba),
        roundTitle: roundName(round.wind, round.roundInWind),
        rounds: roundRows(nav, stop.round),
        step: { count: round.stopCount, index: position.step + 1 },
        table: source.tables[stop.stateIndex],
    };
}
