import { type KanDeclaredEvent, type ReplayEvent } from "@/entities/table";
import { type SeatControlLine } from "@/shared/protocol";

/** What each timeline entry shows: its replay event, the kan a round end's win robbed as declared before it, or a seat control line. */
export type StepEvent = ReplayEvent | KanDeclaredEvent | SeatControlLine;

/**
 * One stop of a replay: it shows the table after entry `stateIndex - 1` (the timeline state `stateIndex`), stops on
 * the move at entry `moveEntry` and tells what entries `firstEntry` to `stateIndex - 1` did.
 */
export interface ActionStep {
    readonly firstEntry: number;
    readonly moveEntry: number;
    readonly stateIndex: number;
}

/** Bookkeeping that belongs to the move before it: a new dora, the riichi stick of the discard just passed. */
const TRAILING_TYPES: ReadonlySet<StepEvent["type"]> = new Set([
    "dora_revealed",
    "riichi_declared",
]);

/** Annotations, which a move's stop tells but never stop on: the game start, a seat changing hands. */
const ANNOTATION_TYPES: ReadonlySet<StepEvent["type"]> = new Set([
    "game_started",
    "ai_replacement",
    "human_return",
]);

function isAnnotation(event: StepEvent): boolean {
    return ANNOTATION_TYPES.has(event.type);
}

/** The event before index `at` that is not an annotation. */
function previousMoveOrBookkeeping(events: readonly StepEvent[], at: number): StepEvent | null {
    for (let index = at - 1; index >= 0; index--) {
        if (!isAnnotation(events[index])) {
            return events[index];
        }
    }
    return null;
}

/** Whether the event at `at` is bookkeeping of the move before it: a new dora, an accepted riichi, a deal's first draw. */
function isTrailing(events: readonly StepEvent[], at: number): boolean {
    const event = events[at];
    if (isAnnotation(event)) {
        return false;
    }
    if (TRAILING_TYPES.has(event.type)) {
        return true;
    }
    return event.type === "draw" && previousMoveOrBookkeeping(events, at)?.type === "round_started";
}

function isStop(events: readonly StepEvent[], at: number): boolean {
    return !isAnnotation(events[at]) && !isTrailing(events, at);
}

/**
 * Where a move's stop ends: past its last bookkeeping entry, annotations between included, so the stop shows the
 * table after its bookkeeping; annotations after its last bookkeeping are left to the next stop.
 */
function batchEnd(events: readonly StepEvent[], start: number): number {
    let end = start;
    for (let index = start; index < events.length; index++) {
        if (isTrailing(events, index)) {
            end = index + 1;
        } else if (!isAnnotation(events[index])) {
            break;
        }
    }
    return end;
}

/** The steps with the entries after the last move, which no move follows, joined to the last stop. */
function withTrailingEntries(steps: ActionStep[], entries: number): ActionStep[] {
    const last = steps.at(-1);
    if (last === undefined || last.stateIndex === entries) {
        return steps;
    }
    return [...steps.slice(0, -1), { ...last, stateIndex: entries }];
}

/**
 * A replay's stops: one per move (a deal with its first draw, a draw, a discard with the riichi it declared, a call, a
 * kan declared open to chankan, a round's result, the game's end), each running through the bookkeeping after it
 * (annotations between included) and telling the annotations before it. Entries after the last move join the last
 * stop.
 */
export function buildActionSteps(events: readonly StepEvent[]): ActionStep[] {
    const steps: ActionStep[] = [];
    let firstEntry = 0;
    for (let index = 0; index < events.length; index++) {
        if (isStop(events, index)) {
            const stateIndex = batchEnd(events, index + 1);
            steps.push({ firstEntry, moveEntry: index, stateIndex });
            firstEntry = stateIndex;
            index = stateIndex - 1;
        }
    }
    return withTrailingEntries(steps, events.length);
}
