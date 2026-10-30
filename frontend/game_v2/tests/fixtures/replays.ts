import {
    type ClientTimeline,
    readReplayTimeline,
    timelineStates,
    timelineStepEvents,
} from "@/entities/client";
import { type StepEvent, type TableState } from "@/entities/table";

const REPLAY_FILES = import.meta.glob("/src/fixtures/replays/*.txt", {
    eager: true,
    import: "default",
    query: "?raw",
});

const REPLAY_DIR = "/src/fixtures/replays/";

export const ENGINE_REPLAYS: ReadonlyMap<string, string> = new Map(
    Object.entries(REPLAY_FILES).map(([path, text]) => [
        path.slice(REPLAY_DIR.length, -".txt".length),
        String(text),
    ]),
);

export function engineReplayText(name: string): string {
    const text = ENGINE_REPLAYS.get(name);
    if (text === undefined) {
        throw new Error(`No engine replay named ${name}`);
    }
    return text;
}

/**
 * An engine replay read through the dispatcher: `events[i]` is entry i's step event, `tables[i + 1]` the table
 * after it.
 */
export interface EngineReplay {
    readonly timeline: ClientTimeline;
    readonly events: readonly StepEvent[];
    readonly tables: readonly TableState[];
}

export function loadEngineReplay(name: string): EngineReplay {
    const read = readReplayTimeline(engineReplayText(name));
    if (!read.ok) {
        throw new Error(`${name}: ${JSON.stringify(read.refusal)}`);
    }
    if (read.damage !== null) {
        throw new Error(`${name}: line ${read.damage.lineNumber}: ${read.damage.detail}`);
    }
    const { timeline } = read;
    return {
        events: timelineStepEvents(timeline),
        tables: timelineStates(timeline).map((state) => state.table),
        timeline,
    };
}
