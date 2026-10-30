import { type ActionStep, type StepEvent, buildActionSteps } from "./action-steps";
import { roundEndPages } from "./handlers/round-end";
import { roundInWind } from "./helpers";
import { type RoundEndResult, type TableState } from "./types";

/** One stop of the replay, in the round it belongs to, with the result pages it shows (a double ron's per winner). */
export interface ReplayStop extends ActionStep {
    readonly round: number;
    readonly pages: number;
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

/** A round from the table its deal shows, its stops, and the table at its last stop. */
function roundOf(
    deal: TableState,
    stops: { readonly first: number; readonly count: number },
    endTable: TableState,
): ReplayRound {
    return {
        dealerSeat: deal.dealerSeat,
        endTable,
        firstStop: stops.first,
        honba: deal.honbaSticks,
        result: endTable.roundEndResult,
        roundInWind: roundInWind(deal),
        stopCount: stops.count,
        wind: deal.roundWind,
    };
}

/** The steps from the first deal on, grouped into rounds, each round starting at its deal. */
function collectRounds(
    events: readonly StepEvent[],
    steps: readonly ActionStep[],
    tables: readonly TableState[],
): { stops: ReplayStop[]; rounds: ReplayRound[] } {
    const stops: ReplayStop[] = [];
    const deals: number[] = [];
    for (const step of steps) {
        if (events[step.moveEntry]?.type === "round_started") {
            deals.push(stops.length);
        }
        if (deals.length > 0) {
            const table = tables[step.stateIndex];
            stops.push({ ...step, pages: resultPages(table), round: deals.length - 1 });
        }
    }
    const rounds = deals.map((firstStop, index) => {
        const end = deals[index + 1] ?? stops.length;
        return roundOf(
            tables[stops[firstStop].moveEntry + 1],
            { count: end - firstStop, first: firstStop },
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
