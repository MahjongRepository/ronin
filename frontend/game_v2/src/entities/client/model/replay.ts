import {
    DesyncError,
    type ReplayFileLine,
    type ReplayLineError,
    type ReplayRefusal,
    type ReplaySource,
    type StepEvent,
    buildNavigationIndex,
    isReplayEvent,
    isSeatControlLine,
    readReplayFile,
} from "@/entities/table";

import { startReplayClient, traceReplayClient } from "./dispatch";
import { type ClientTimeline, type TimelineEntry, timelineStates } from "./timeline";
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

function stepEventOf(parsed: TimelineEntry["parsed"]): StepEvent {
    if (parsed !== null) {
        if (parsed.type === "kan_declared" || isSeatControlLine(parsed) || isReplayEvent(parsed)) {
            return parsed;
        }
    }
    throw new Error(`A replay timeline entry shows no replay event: ${parsed?.type ?? "none"}`);
}

/**
 * The step event of each timeline entry, for the replay's stops: its replay event, the kan a round end robbed as
 * declared, or a seat control line. The reader keeps no other entry, so any other throws.
 */
export function timelineStepEvents(timeline: ClientTimeline): StepEvent[] {
    return timeline.entries.map(({ parsed }) => stepEventOf(parsed));
}

/** A replay ready for its page: what it shows, and the seats a viewer may look from. */
export interface LoadedReplay extends ReplaySource {
    /** The recorded first dealer's seat, the default seat at the bottom (`docs/architecture.md`, Replays). */
    readonly firstDealerSeat: number;
    readonly seatCount: number;
}

/** A replay the page cannot show: refused by its version line, or holding no deal to open on. */
export type ReplayUnshowable =
    | ReplayRefusal
    | { readonly kind: "no_deal"; readonly damage: ReplayLineError | null };

export type ReplayRead =
    | { readonly ok: true; readonly replay: LoadedReplay }
    | { readonly ok: false; readonly unshowable: ReplayUnshowable };

/** Each timeline state's table, and the calls it shows. */
function timelineTablesAndCalls(timeline: ClientTimeline): Pick<ReplaySource, "calls" | "tables"> {
    const states = timelineStates(timeline);
    return {
        calls: states.map((state) => state.calls?.calls ?? []),
        tables: states.map((state) => state.table),
    };
}

/** Read a replay file for its page: its timeline, its stops by round from the first deal, and where it broke off. */
export function readReplay(text: string): ReplayRead {
    const read = readReplayTimeline(text);
    if (!read.ok) {
        return { ok: false, unshowable: read.refusal };
    }
    const events = timelineStepEvents(read.timeline);
    const { calls, tables } = timelineTablesAndCalls(read.timeline);
    const navigation = buildNavigationIndex(events, tables);
    if (navigation.rounds.length === 0) {
        return { ok: false, unshowable: { damage: read.damage, kind: "no_deal" } };
    }
    const last = tables[tables.length - 1];
    return {
        ok: true,
        replay: {
            calls,
            damage: read.damage,
            events,
            firstDealerSeat: last.firstDealerSeat,
            navigation,
            seatCount: last.players.length,
            tables,
        },
    };
}
