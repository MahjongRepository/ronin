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
 * dispatcher, of a client with no session and no viewer, so every hand the file records is known.
 */
export function readReplayTimeline(text: string): ReplayTimelineRead {
    const file = readReplayFile(text);
    if (!file.ok) {
        return file;
    }
    const events = file.lines.map(({ raw }): ClientEvent => ({
        at: REPLAY_TIME,
        kind: "replay_line",
        raw,
    }));
    const timeline = buildClientTimeline(startReplayClient(REPLAY_TIME), events);
    const lineErrors = timeline.entries.flatMap((entry, index): ReplayLineError[] =>
        entry.effects.flatMap((effect) =>
            effect.type === "report_parse_error"
                ? [{ detail: effect.detail, lineNumber: file.lines[index].lineNumber }]
                : [],
        ),
    );
    const errors = [...file.errors, ...lineErrors]
        .toSorted((left, right) => left.lineNumber - right.lineNumber)
        .map(({ detail, lineNumber }) => `Line ${lineNumber}: ${detail}`);
    return { errors, ok: true, timeline };
}

/** The replay event of each timeline entry, for the replay's stop points; any other entry moves no step. */
export function timelineStepEvents(timeline: ClientTimeline): StepEvent[] {
    return timeline.entries.map(({ parsed }) =>
        parsed !== null && isReplayEvent(parsed) ? parsed : null,
    );
}
