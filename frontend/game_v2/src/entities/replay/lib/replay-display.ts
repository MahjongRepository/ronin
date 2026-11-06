import { type NavigationIndex } from "@/entities/replay/model/navigation-index";
import { type ShownReplayCall } from "@/entities/replay/model/replay-calls";
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
    type BoardDisplayState,
    type BoardMotionCue,
    type BoardPerspective,
    type Call,
    type ReplayLineError,
    type TablePanel,
    type TableState,
    boardCallouts,
    formatRoundName,
    replaySeatingPanel,
    roundResultSummary,
    tablePanel,
    tableStateToDisplayState,
} from "@/entities/table";
import { t } from "@/shared/i18n";

/** A replay that is not the whole game: a short label, and why. */
export interface ReplayIncompleteness {
    readonly label: string;
    readonly detail: string;
}

/**
 * A replay as its page reads it: its tables with the calls each state shows (index by index), its navigation, where
 * it broke off, and the table its seating shows.
 */
export interface ReplaySource {
    readonly tables: readonly TableState[];
    /**
     * The table as the game started, seated before its first deal, each seat at the score its first deal starts it
     * on (the game's start names none): the seating the page opens on.
     */
    readonly startTable: TableState;
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

/** What a replay page shows at a cursor: the board and the panel over it, where it stands and where it can go. */
export interface ReplayDisplay {
    readonly matchResult: boolean;
    readonly motion: BoardMotionCue;
    /** The stop's board, or the table as the game started under its seating. */
    readonly board: BoardDisplayState | null;
    /** The panel over the board: the seating, a round's result at the cursor's page, the game's end; else null. */
    readonly overlay: TablePanel | null;
    /** The calls the stop's own move made, by their seats from the perspective's; null for a move that made none. */
    readonly callouts: BoardCallouts | null;
    readonly roundName: string;
    readonly step: { readonly index: number; readonly count: number };
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
            detail: t("replay.incomplete.damaged_detail", { record: source.damage.lineNumber }),
            label: t("replay.incomplete.damaged"),
        };
    }
    if (source.navigation.complete) {
        return null;
    }
    return { detail: t("replay.incomplete.detail"), label: t("replay.incomplete.label") };
}

function endNotice(source: ReplaySource, cursor: ReplayCursor): string | null {
    if (incompleteness(source) === null || cursor.stop !== source.navigation.stops.length - 1) {
        return null;
    }
    return source.damage === null
        ? t("replay.incomplete.ends_here")
        : t("replay.incomplete.damaged_stops_here", { record: source.damage.lineNumber });
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

/**
 * The calls shown, keyed by their stop and the time they were shown from, so arriving on their stop plays them afresh
 * while turning its pages or moving on past it does not.
 */
function shownCallouts(
    source: ReplaySource,
    shown: ShownReplayCall | null,
    perspective: BoardPerspective,
): BoardCallouts | null {
    if (shown === null) {
        return null;
    }
    const { stateIndex } = source.navigation.stops[shown.stop];
    const calls: readonly Call[] = source.calls[stateIndex] ?? [];
    if (calls.length === 0) {
        return null;
    }
    return {
        announced: shown.announce,
        items: boardCallouts(calls, perspective.bottomSeat),
        key: `call-${shown.stop}-${shown.at}`,
    };
}

/** Where the page stands: at a stop, or on the seating over the table as the game started, before any stop. */
export interface ReplayPlace {
    readonly cursor: ReplayCursor;
    readonly perspective: BoardPerspective;
    /** The seating shows, while the replay waits for its reader at its start. */
    readonly seating: boolean;
    readonly shownCall: ShownReplayCall | null;
}

/** The stop's board and panel, or the seating over the table as the game started, which shows no call. */
function stopBoard(
    source: ReplaySource,
    { cursor, perspective, seating, shownCall }: ReplayPlace,
): Pick<ReplayDisplay, "board" | "callouts" | "overlay" | "matchResult"> {
    if (seating) {
        return {
            board: tableStateToDisplayState(source.startTable, perspective),
            callouts: null,
            matchResult: false,
            overlay: replaySeatingPanel(source.startTable),
        };
    }
    const { stateIndex } = source.navigation.stops[cursor.stop];
    const table = source.tables[stateIndex];
    const callouts = shownCallouts(source, shownCall, perspective);
    const overlay = tablePanel(table, {
        callouts,
        overGameEnd: false,
        page: cursor.page,
        viewerSeat: null,
    });
    return {
        board: tableStateToDisplayState(table, perspective),
        callouts,
        matchResult: overlay?.kind === "game_end",
        overlay,
    };
}

/** What the page shows at its place: the board and its panel, the round and step and the moves. */
export function replayDisplay(source: ReplaySource, place: ReplayPlace): ReplayDisplay {
    const { cursor } = place;
    const nav = source.navigation;
    const stop = nav.stops[cursor.stop];
    const round = cursorRound(nav, cursor);
    const position = roundPosition(nav, cursor);
    return {
        ...stopBoard(source, place),
        endNotice: endNotice(source, cursor),
        incomplete: incompleteness(source),
        motion: { mode: "replay", sequence: place.seating ? -1 : cursor.stop },
        moves: replayMoves(nav, cursor),
        roundName: formatRoundName(round.wind, round.roundInWind, round.honba),
        rounds: roundRows(nav, stop.round),
        step: { count: round.stopCount, index: position.step + 1 },
    };
}
