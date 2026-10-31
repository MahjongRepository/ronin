import {
    DesyncError,
    type ReplayFileLine,
    type ReplayLineError,
    type ReplayRefusal,
    readReplayFile,
} from "@/entities/table";

import { startReplayClient, traceReplayClient } from "./dispatch";
import { type ClientTimeline, type TimelineEntry } from "./timeline";
import { type ReplayClient } from "./types";

/** The logical time of every replay line: a replay records no times, and its client waits on no deadline. */
const REPLAY_TIME = 0;

/**
 * A replay read into a timeline, up to its first line that could not be shown (`damage`: unreadable, or impossible
 * on the table it reaches), since every later state would build on a table that missed it; or refused by its version
 * line.
 */
export type ReplayTimelineRead =
    | {
          readonly ok: true;
          readonly timeline: ClientTimeline<ReplayClient>;
          readonly damage: ReplayLineError | null;
      }
    | { readonly ok: false; readonly refusal: ReplayRefusal };

interface LineSteps {
    readonly entries: readonly TimelineEntry<ReplayClient>[];
    readonly damage: string | null;
}

/**
 * The timeline entries one line makes, or why it cannot be shown: it does not parse, or the table refuses it (a
 * `DesyncError`). Any other error is the client's own and propagates to the view's failure screen.
 */
function stepLine(state: ReplayClient, line: ReplayFileLine): LineSteps {
    const event = { at: REPLAY_TIME, kind: "replay_line", raw: line.raw } as const;
    try {
        const steps = traceReplayClient(state, event);
        const refused = steps
            .flatMap((step) => step.effects)
            .find((effect) => effect.type === "report_protocol_failure");
        if (refused !== undefined) {
            return { damage: refused.detail, entries: [] };
        }
        return {
            damage: null,
            entries: steps.map((step) => ({
                effects: step.effects,
                event,
                parsed: step.parsed,
                state: step.state,
            })),
        };
    } catch (error: unknown) {
        if (!(error instanceof DesyncError)) {
            throw error;
        }
        return { damage: `Cannot be played: ${error.message}`, entries: [] };
    }
}

/** The entries of every line in order, up to the first that cannot be shown, which is the damage. */
function stepLines(
    start: ReplayClient,
    lines: readonly ReplayFileLine[],
): { readonly entries: TimelineEntry<ReplayClient>[]; readonly damage: ReplayLineError | null } {
    const entries: TimelineEntry<ReplayClient>[] = [];
    let state = start;
    for (const line of lines) {
        const stepped = stepLine(state, line);
        if (stepped.damage !== null) {
            return { damage: { detail: stepped.damage, lineNumber: line.lineNumber }, entries };
        }
        entries.push(...stepped.entries);
        state = entries.at(-1)?.state ?? state;
    }
    return { damage: null, entries };
}

/**
 * Read a replay file into the dispatcher's timeline: each event line is a replay line event, parsed by the
 * dispatcher, of a client with no session and no viewer, so every hand the file records is known. A line the
 * dispatcher takes in parts makes an entry per part. Reading stops at the first line that is not a JSON object, does
 * not parse, or is impossible on the table so far.
 */
export function readReplayTimeline(text: string): ReplayTimelineRead {
    const file = readReplayFile(text);
    if (!file.ok) {
        return file;
    }
    const firstUnreadable = file.errors.at(0) ?? null;
    const readable =
        firstUnreadable === null
            ? file.lines
            : file.lines.filter((line) => line.lineNumber < firstUnreadable.lineNumber);
    const start = startReplayClient(REPLAY_TIME);
    const stepped = stepLines(start, readable);
    return {
        damage: stepped.damage ?? firstUnreadable,
        ok: true,
        timeline: { entries: stepped.entries, start },
    };
}
