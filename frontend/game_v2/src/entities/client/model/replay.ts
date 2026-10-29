import {
    type ReplayLineError,
    type StepEvent,
    isReplayEvent,
    readReplayFile,
} from "@/entities/table";

import { startReplayClient } from "./dispatch";
import { type ClientTimeline, buildClientTimeline } from "./timeline";
import { type ClientEvent } from "./types";

/** The logical time of every replay line: a replay records no times, and its client waits on no deadline. */
const REPLAY_TIME = 0;

/**
 * A replay read into a timeline beside every line that could not be shown, as `Line <n>: <why>` in file order, or
 * refused by its version line.
 */
export type ReplayTimelineRead =
    | {
          readonly ok: true;
          readonly timeline: ClientTimeline;
          readonly errors: readonly string[];
      }
    | { readonly ok: false; readonly refusal: string };

/**
 * Read a replay file into the dispatcher's timeline: each event line is a replay line event, parsed by the
 * dispatcher, of a client with no session and no viewer, so every hand the file records is known. A line the
 * dispatcher takes in parts makes an entry per part, so an error names the line its entry's event came from.
 */
export function readReplayTimeline(text: string): ReplayTimelineRead {
    const file = readReplayFile(text);
    if (!file.ok) {
        return file;
    }
    const lineNumbers = new Map(
        file.lines.map(({ lineNumber, raw }): [ClientEvent, number] => [
            { at: REPLAY_TIME, kind: "replay_line", raw },
            lineNumber,
        ]),
    );
    const timeline = buildClientTimeline(startReplayClient(REPLAY_TIME), [...lineNumbers.keys()]);
    const lineErrors = timeline.entries.flatMap(({ effects, event }): ReplayLineError[] => {
        const lineNumber = lineNumbers.get(event);
        if (lineNumber === undefined) {
            throw new Error("A replay timeline entry came from no line of its file");
        }
        return effects.flatMap((effect) =>
            effect.type === "report_parse_error" ? [{ detail: effect.detail, lineNumber }] : [],
        );
    });
    const errors = [...file.errors, ...lineErrors]
        .toSorted((left, right) => left.lineNumber - right.lineNumber)
        .map(({ detail, lineNumber }) => `Line ${lineNumber}: ${detail}`);
    return { errors, ok: true, timeline };
}

/**
 * The step event of each timeline entry, for the replay's stop points: its replay event, or the kan a round end
 * robbed as declared; any other entry moves no step.
 */
export function timelineStepEvents(timeline: ClientTimeline): StepEvent[] {
    return timeline.entries.map(({ parsed }) => {
        if (parsed === null) {
            return null;
        }
        return parsed.type === "kan_declared" || isReplayEvent(parsed) ? parsed : null;
    });
}
