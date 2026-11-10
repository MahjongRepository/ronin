import { type RoundEndResult, type TableState, roundEndPages } from "@/entities/table";

import { type ActionStep, type StepEvent, buildActionSteps } from "./action-steps";

/**
 * One stop of the replay, in the round it belongs to, with the result pages it shows (a double ron's per winner) and
 * the seat whose turn it starts: the stop that gives a seat the tile it acts on (its deal as dealer, a draw, a call of
 * a discard), null for any other, a draw after the seat's own kan included.
 */
export interface ReplayStop extends ActionStep {
    readonly round: number;
    readonly pages: number;
    readonly turnSeat: number | null;
}

/** One recorded deal, repeats counted: its stops are `firstStop` up to the next round's. */
export interface ReplayRound {
    readonly firstStop: number;
    readonly stopCount: number;
    readonly wind: number;
    /** The round's number within its wind, from 1 (the wire's round number counts every deal). */
    readonly roundInWind: number;
    readonly honba: number;
    readonly dealerSeat: number;
    /** The round's result, or null when the recording stops before it. */
    readonly result: RoundEndResult | null;
    /** The stop that shows the round's result, or null when the recording stops before it. */
    readonly resultStop: number | null;
    /** The table at the round's last stop, after its payments: the names and scores its result reads. */
    readonly endTable: TableState;
}

/**
 * Where a replay can stop, from the first deal: every stop and every round. `complete` says whether the recording
 * reaches the game's end; a replay that stops short of it holds what was recorded and no more.
 */
export interface NavigationIndex {
    readonly stops: readonly ReplayStop[];
    readonly rounds: readonly ReplayRound[];
    readonly complete: boolean;
}

function resultPages(table: TableState): number {
    if (table.phase !== "round_ended" || table.roundEndResult === null) {
        return 1;
    }
    return roundEndPages(table.roundEndResult).length;
}

/** A round from the table its deal shows, its stops, the one showing its result, and the table at its last stop. */
function roundOf(
    deal: TableState,
    stops: { readonly first: number; readonly count: number; readonly result: number | null },
    endTable: TableState,
): ReplayRound {
    return {
        dealerSeat: deal.dealerSeat,
        endTable,
        firstStop: stops.first,
        honba: deal.honbaSticks,
        result: endTable.roundEndResult,
        resultStop: stops.result,
        roundInWind: deal.roundInWind,
        stopCount: stops.count,
        wind: deal.roundWind,
    };
}

/** The seat the move at `entry` hands the turn to, or null for a move that hands it to nobody. */
function turnTaker(
    events: readonly StepEvent[],
    tables: readonly TableState[],
    entry: number,
): number | null {
    const event = events[entry];
    switch (event.type) {
        case "round_started": {
            return tables[entry + 1].dealerSeat;
        }
        case "draw": {
            return event.seat;
        }
        case "meld": {
            return event.callerSeat;
        }
        default: {
            return null;
        }
    }
}

/**
 * The seat whose turn each step starts, null for a step that starts none: a seat already acting (a draw after its own
 * kan) starts no turn again until it discards or a new deal begins.
 */
function turnSeats(
    events: readonly StepEvent[],
    steps: readonly ActionStep[],
    tables: readonly TableState[],
): (number | null)[] {
    let acting: number | null = null;
    return steps.map((step) => {
        const moveType = events[step.moveEntry]?.type;
        const taker = turnTaker(events, tables, step.moveEntry);
        const turnSeat = moveType === "round_started" || taker !== acting ? taker : null;
        acting = moveType === "discard" ? null : (taker ?? acting);
        return turnSeat;
    });
}

/** The steps from the first deal on, grouped into rounds, each round starting at its deal. */
function collectRounds(
    events: readonly StepEvent[],
    steps: readonly ActionStep[],
    tables: readonly TableState[],
): { stops: ReplayStop[]; rounds: ReplayRound[] } {
    const stops: ReplayStop[] = [];
    const deals: number[] = [];
    const turns = turnSeats(events, steps, tables);
    for (const [index, step] of steps.entries()) {
        if (events[step.moveEntry]?.type === "round_started") {
            deals.push(stops.length);
        }
        if (deals.length > 0) {
            stops.push({
                ...step,
                pages: resultPages(tables[step.stateIndex]),
                round: deals.length - 1,
                turnSeat: turns[index],
            });
        }
    }
    const rounds = deals.map((firstStop, index) => {
        const end = deals[index + 1] ?? stops.length;
        const resultAt = stops
            .slice(firstStop, end)
            .findIndex((stop) => tables[stop.stateIndex].phase === "round_ended");
        return roundOf(
            tables[stops[firstStop].moveEntry + 1],
            {
                count: end - firstStop,
                first: firstStop,
                result: resultAt === -1 ? null : firstStop + resultAt,
            },
            tables[stops[end - 1].stateIndex],
        );
    });
    return { rounds, stops };
}

/**
 * The replay's navigation from its timeline: `events[i]` is entry i's step event and `tables[i + 1]` the table after
 * it. It opens on the first deal: the game start and anything before the first deal show from there.
 */
export function buildNavigationIndex(
    events: readonly StepEvent[],
    tables: readonly TableState[],
): NavigationIndex {
    const { rounds, stops } = collectRounds(events, buildActionSteps(events), tables);
    const last = stops.at(-1);
    const complete = last !== undefined && events[last.moveEntry]?.type === "game_end";
    return { complete, rounds, stops };
}
