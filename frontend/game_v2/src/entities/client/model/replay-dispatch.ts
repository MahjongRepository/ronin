import {
    type TableEvent,
    applyEvent,
    createInitialTableState,
    replayLineTableEvent,
} from "@/entities/table";
import { type ReplayLine, parseReplayLine } from "@/shared/protocol";

import { callsAt, replayCalls } from "./calls";
import { type ReplayClient, type ReplayLineEvent, type TracedStep } from "./types";

function reportProtocolFailure(state: ReplayClient, detail: string): TracedStep<ReplayClient> {
    return {
        effects: [{ detail, type: "report_protocol_failure" }],
        parsed: null,
        state,
    };
}

/** A replay line's step: its table event applied, and the calls the move makes. */
function replayLineStep(
    state: ReplayClient,
    line: ReplayLine,
    event: TableEvent,
): TracedStep<ReplayClient> {
    const table = applyEvent(state.table, event);
    const calls = replayCalls(state, event, table);
    return { effects: [], parsed: line, state: { ...state, calls, table } };
}

/** A replay file's line: a replay event or seat control line moves the table; any other is reported. */
function onReplayLine(state: ReplayClient, raw: Record<string, unknown>): TracedStep<ReplayClient> {
    const [error, line] = parseReplayLine(raw);
    if (error) {
        return reportProtocolFailure(state, `Parse error: ${error.message}`);
    }
    const tableEvent = replayLineTableEvent(line);
    if (tableEvent === null) {
        return reportProtocolFailure(state, `Non-replay event type: ${line.type}`);
    }
    return replayLineStep(state, line, tableEvent);
}

/** Begin a replay's client at logical time `at`: no session, no viewer, nothing it could send. */
export function startReplayClient(at: number): ReplayClient {
    return { calls: null, kind: "replay", now: at, table: createInitialTableState() };
}

/**
 * A replay's step over one line of its file, with what it took of the line, as parsed: the line's table event and the
 * calls it makes, a replay having nothing else to take.
 */
export function traceReplayClient(
    state: ReplayClient,
    event: ReplayLineEvent,
): TracedStep<ReplayClient> {
    const step = onReplayLine({ ...state, now: event.at }, event.raw);
    return { ...step, state: { ...step.state, calls: callsAt(step.state.calls, event.at) } };
}
