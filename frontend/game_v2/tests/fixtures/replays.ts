import {
    type ClientTimeline,
    readReplayTimeline,
    timelineStates,
    timelineStepEvents,
} from "@/entities/client";
import { type StepEvent, type TableState } from "@/entities/table";

const REPLAY_FILES = import.meta.glob("./replays/*.txt", {
    eager: true,
    import: "default",
    query: "?raw",
});

export const ENGINE_REPLAYS: ReadonlyMap<string, string> = new Map(
    Object.entries(REPLAY_FILES).map(([path, text]) => [
        path.slice("./replays/".length, -".txt".length),
        text,
    ]),
);

/**
 * An engine replay read through the dispatcher: `events[i]` is entry i's replay event, `tables[i + 1]` the table
 * after it.
 */
export interface EngineReplay {
    readonly timeline: ClientTimeline;
    readonly events: readonly StepEvent[];
    readonly tables: readonly TableState[];
}

export function loadEngineReplay(name: string): EngineReplay {
    const text = ENGINE_REPLAYS.get(name);
    if (text === undefined) {
        throw new Error(`No engine replay named ${name}`);
    }
    const read = readReplayTimeline(text);
    if (!read.ok) {
        throw new Error(`${name}: ${read.refusal}`);
    }
    if (read.errors.length > 0) {
        throw new Error(`${name}: ${read.errors.join("; ")}`);
    }
    const { timeline } = read;
    return {
        events: timelineStepEvents(timeline),
        tables: timelineStates(timeline).map((state) => state.table),
        timeline,
    };
}
