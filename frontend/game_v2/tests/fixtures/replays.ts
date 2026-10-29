import { type ReplayEvent, parseReplayLines } from "@/entities/table";

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

export function loadEngineReplay(name: string): readonly ReplayEvent[] {
    const text = ENGINE_REPLAYS.get(name);
    if (text === undefined) {
        throw new Error(`No engine replay named ${name}`);
    }
    const parsed = parseReplayLines(text);
    if (!parsed.ok) {
        throw new Error(`${name}: ${parsed.refusal}`);
    }
    if (parsed.errors.length > 0) {
        throw new Error(`${name}: ${parsed.errors.join("; ")}`);
    }
    return parsed.events;
}
