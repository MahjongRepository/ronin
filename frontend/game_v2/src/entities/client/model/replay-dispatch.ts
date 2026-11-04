import {
    type TableEvent,
    applyEvent,
    createInitialTableState,
    replayLineTableEvent,
    robbedKanDeclared,
} from "@/entities/table";
import { type ReplayLine, parseReplayLine } from "@/shared/protocol";

import { callsAt, replayCalls } from "./calls";
import { type ReplayClient, type ReplayLineEvent, type TracedStep } from "./types";

/**
 * A replay's step as a part of its line: a partial one took only part of it (the kan a round end robbed, declared),
 * so the dispatcher steps the same line again for the rest.
 */
interface ReplayPart extends TracedStep<ReplayClient> {
    readonly partial: boolean;
}

function reportProtocolFailure(state: ReplayClient, detail: string): ReplayPart {
    return {
        effects: [{ detail, type: "report_protocol_failure" }],
        parsed: null,
        partial: false,
        state,
    };
}

/**
 * The first part of a replay's round end that robbed a kan the table does not show yet: the kan declared, as a part
 * of its own, since the replay records no line for the declaration. Null for any other line.
 */
function robbedKanPart(state: ReplayClient, line: ReplayLine): ReplayPart | null {
    const declared = line.type === "round_end" ? robbedKanDeclared(line) : null;
    if (declared === null) {
        return null;
    }
    const table = applyEvent(state.table, declared);
    if (table === state.table) {
        return null;
    }
    const calls = replayCalls(state, declared, table);
    return { effects: [], parsed: declared, partial: true, state: { ...state, calls, table } };
}

/** A replay line's whole step: its table event applied, and the calls the move makes. */
function replayLineStep(state: ReplayClient, line: ReplayLine, event: TableEvent): ReplayPart {
    const table = applyEvent(state.table, event);
    const calls = replayCalls(state, event, table);
    return { effects: [], parsed: line, partial: false, state: { ...state, calls, table } };
}

/**
 * A replay file's line: a replay event or seat control line moves the table; any other is reported. A round end that
 * robbed a kan is taken in two parts, the kan declared and then the result, so a replay stops on the kan.
 */
function onReplayLine(state: ReplayClient, raw: Record<string, unknown>): ReplayPart {
    const [error, line] = parseReplayLine(raw);
    if (error) {
        return reportProtocolFailure(state, `Parse error: ${error.message}`);
    }
    const tableEvent = replayLineTableEvent(line);
    if (tableEvent === null) {
        return reportProtocolFailure(state, `Non-replay event type: ${line.type}`);
    }
    return robbedKanPart(state, line) ?? replayLineStep(state, line, tableEvent);
}

/** Begin a replay's client at logical time `at`: no session, no viewer, nothing it could send. */
export function startReplayClient(at: number): ReplayClient {
    return { calls: null, kind: "replay", now: at, table: createInitialTableState() };
}

/**
 * A replay's step over one line of its file, as the parts it took, each with what it took of the line, as parsed: one
 * part, but two for a round end that robbed a kan (the kan declared, then the result), the second finding the kan
 * shown, so the parts always end. A part is the line's table event and the calls it makes, a replay having nothing
 * else to take.
 */
export function traceReplayClient(
    state: ReplayClient,
    event: ReplayLineEvent,
): readonly TracedStep<ReplayClient>[] {
    const step = onReplayLine({ ...state, now: event.at }, event.raw);
    const part = { ...step, state: { ...step.state, calls: callsAt(step.state.calls, event.at) } };
    return part.partial ? [part, ...traceReplayClient(part.state, event)] : [part];
}
