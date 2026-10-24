import { type ActionStep } from "./action-steps";
import { type ReplayEvent, type TableState } from "./types";

export interface RoundInfo {
    /** Index into the actionSteps array where this round's round_started lands */
    actionStepIndex: number;
    /** Round wind (0=East, 1=South, etc.) */
    wind: number;
    /** Round number within the wind */
    roundNumber: number;
    /** Honba stick count */
    honba: number;
    /** Human-readable result description from round_end (empty if game ended mid-round).
     *  Derived from TableState.lastEventDescription of the round_end state. */
    resultDescription: string;
}

export interface TurnInfo {
    /** Index into the actionSteps array where this draw lands */
    actionStepIndex: number;
    /** Sequential turn number within the round (1-based) */
    turnNumber: number;
    /** Name of the player who drew */
    playerName: string;
}

export interface NavigationIndex {
    /** All rounds in the game */
    rounds: RoundInfo[];
    /** Maps each action step index to index in rounds[] (-1 if step is before any round or after game end) */
    stepToRoundIndex: number[];
    /** Turns within each round, indexed by round index in rounds[] */
    turnsByRound: TurnInfo[][];
}

/** Builds a map from event index to action step index. */
function buildEventToStepMap(actionSteps: ActionStep[]): Map<number, number> {
    const map = new Map<number, number>();
    for (let stepIdx = 1; stepIdx < actionSteps.length; stepIdx++) {
        const eventIndex = actionSteps[stepIdx].descriptionStateIndex - 1;
        map.set(eventIndex, stepIdx);
    }
    return map;
}

/** Scans ahead from a round_started event to find the result description from the next round_end. */
function findRoundResultDescription(
    events: ReplayEvent[],
    states: TableState[],
    startIdx: number,
): string {
    for (let idx = startIdx + 1; idx < events.length; idx++) {
        if (events[idx].type === "round_end") {
            const roundEndStateIdx = idx + 1;
            if (roundEndStateIdx < states.length) {
                return states[roundEndStateIdx].lastEventDescription;
            }
            return "";
        }
        if (events[idx].type === "round_started") {
            return "";
        }
    }
    return "";
}

/** Collects all rounds from the event stream. */
function collectRounds(
    events: ReplayEvent[],
    states: TableState[],
    eventToStepIndex: Map<number, number>,
): RoundInfo[] {
    const rounds: RoundInfo[] = [];

    for (let eventIdx = 0; eventIdx < events.length; eventIdx++) {
        const event = events[eventIdx];
        if (event.type === "round_started") {
            const stepIdx = eventToStepIndex.get(eventIdx);
            if (stepIdx !== undefined) {
                rounds.push({
                    actionStepIndex: stepIdx,
                    honba: event.honbaSticks,
                    resultDescription: findRoundResultDescription(events, states, eventIdx),
                    roundNumber: event.roundNumber,
                    wind: event.wind,
                });
            }
        }
    }

    return rounds;
}

/** Resolves player name from the state after a draw event. */
function resolvePlayerName(states: TableState[], stateIdx: number, seat: number): string {
    if (stateIdx >= states.length) {
        return `Seat ${seat}`;
    }
    return states[stateIdx].players.find((p) => p.seat === seat)?.name ?? `Seat ${seat}`;
}

interface EventRange {
    endEventIdx: number;
    startEventIdx: number;
}

interface TurnCollectionContext {
    eventToStepIndex: Map<number, number>;
    events: ReplayEvent[];
    states: TableState[];
}

/** Collects all turns (draw events) within a range of events for a single round. */
function collectTurnsForRange(ctx: TurnCollectionContext, range: EventRange): TurnInfo[] {
    const turns: TurnInfo[] = [];
    let turnNumber = 1;

    for (let eventIdx = range.startEventIdx; eventIdx < range.endEventIdx; eventIdx++) {
        const event = ctx.events[eventIdx];
        if (event.type === "draw") {
            const stepIdx = ctx.eventToStepIndex.get(eventIdx);
            if (stepIdx !== undefined) {
                turns.push({
                    actionStepIndex: stepIdx,
                    playerName: resolvePlayerName(ctx.states, eventIdx + 1, event.seat),
                    turnNumber,
                });
                turnNumber++;
            }
        }
    }

    return turns;
}

/** Checks whether a given action step corresponds to a game_end event. */
function isGameEndStep(stepIdx: number, actionSteps: ActionStep[], events: ReplayEvent[]): boolean {
    if (stepIdx <= 0) {
        return false;
    }
    const eventIdx = actionSteps[stepIdx].descriptionStateIndex - 1;
    return eventIdx >= 0 && eventIdx < events.length && events[eventIdx].type === "game_end";
}

/** Builds turnsByRound: for each round, collects draw events mapped to TurnInfo. */
function buildTurnsByRound(
    ctx: TurnCollectionContext,
    rounds: RoundInfo[],
    actionSteps: ActionStep[],
): TurnInfo[][] {
    return rounds.map((_round, roundIdx) => {
        const startEventIdx =
            actionSteps[rounds[roundIdx].actionStepIndex].descriptionStateIndex - 1;
        const endEventIdx =
            roundIdx + 1 < rounds.length
                ? actionSteps[rounds[roundIdx + 1].actionStepIndex].descriptionStateIndex - 1
                : ctx.events.length;
        return collectTurnsForRange(ctx, { endEventIdx, startEventIdx });
    });
}

/** Maps each action step to its parent round index (-1 for steps outside any round). */
function buildStepToRoundIndex(
    rounds: RoundInfo[],
    actionSteps: ActionStep[],
    events: ReplayEvent[],
): number[] {
    const stepToRoundIndex: number[] = new Array(actionSteps.length).fill(-1);

    for (let roundIdx = 0; roundIdx < rounds.length; roundIdx++) {
        const startStep = rounds[roundIdx].actionStepIndex;
        const endStep =
            roundIdx + 1 < rounds.length
                ? rounds[roundIdx + 1].actionStepIndex
                : actionSteps.length;

        for (let stepIdx = startStep; stepIdx < endStep; stepIdx++) {
            if (!isGameEndStep(stepIdx, actionSteps, events)) {
                stepToRoundIndex[stepIdx] = roundIdx;
            }
        }
    }

    return stepToRoundIndex;
}

/**
 * Builds a navigation index from replay events, action steps, and computed states.
 *
 * Scans events to identify round boundaries (round_started) and turns (draw events),
 * then maps each action step to its parent round for O(1) lookup.
 */
export function buildNavigationIndex(
    events: ReplayEvent[],
    actionSteps: ActionStep[],
    states: TableState[],
): NavigationIndex {
    const eventToStepIndex = buildEventToStepMap(actionSteps);
    const rounds = collectRounds(events, states, eventToStepIndex);
    const ctx: TurnCollectionContext = { eventToStepIndex, events, states };
    const turnsByRound = buildTurnsByRound(ctx, rounds, actionSteps);
    const stepToRoundIndex = buildStepToRoundIndex(rounds, actionSteps, events);

    return { rounds, stepToRoundIndex, turnsByRound };
}

/** Looks up the round for a given action step index. */
export function roundForStep(navIndex: NavigationIndex, step: number): RoundInfo | undefined {
    const roundIdx = navIndex.stepToRoundIndex[step];
    if (roundIdx === undefined || roundIdx === -1) {
        return undefined;
    }
    return navIndex.rounds[roundIdx];
}

/** Returns the turns within the round that contains the given action step. */
export function turnsForStep(navIndex: NavigationIndex, step: number): TurnInfo[] {
    const roundIdx = navIndex.stepToRoundIndex[step];
    if (roundIdx === undefined || roundIdx === -1) {
        return [];
    }
    return navIndex.turnsByRound[roundIdx] ?? [];
}
