import { type ReplayEvent, type TableEvent } from "@/entities/table/model/types";
import { REPLAY_VERSION, type ReplayLine, type SeatControlLine, WIRE_KEY } from "@/shared/protocol";

import { MAX_REPLAY_BYTES, decodeReplayRecords } from "./replay-codec";

const REPLAY_EVENT_TYPES: Record<ReplayEvent["type"], true> = {
    discard: true,
    dora_revealed: true,
    draw: true,
    game_end: true,
    game_started: true,
    meld: true,
    riichi_declared: true,
    round_end: true,
    round_started: true,
};

const SEAT_CONTROL_LINE_TYPES: Record<SeatControlLine["type"], true> = {
    ai_replacement: true,
    human_return: true,
};

/** An event line of a replay file as an object, still to be parsed, with its 1-based record number in the file. */
export interface ReplayFileLine {
    readonly lineNumber: number;
    readonly raw: Readonly<Record<string, unknown>>;
}

/** A line of a replay file that could not be read, by its 1-based record number. */
export interface ReplayLineError {
    readonly lineNumber: number;
    readonly detail: string;
}

/** A replay file's event records, beside its first damaged record. */
export interface ReplayFileLines {
    readonly lines: readonly ReplayFileLine[];
    readonly errors: readonly ReplayLineError[];
}

export type ReplayRecordFailure =
    | { readonly kind: "incomplete_record"; readonly record: number }
    | { readonly kind: "invalid_record"; readonly record: number; readonly cause: unknown };

/**
 * Why a replay file is refused before any event line: it holds no version line this client can read, or one naming
 * another version, whose lines may mean something else.
 */
export type ReplayRefusal =
    | { readonly kind: "empty" }
    | { readonly kind: "no_version_record" }
    | { readonly kind: "too_large" }
    | ReplayRecordFailure
    | { readonly kind: "unsupported_version"; readonly version: string };

/** A replay file read whole, or refused before any event line because of its version line. */
export type ReplayFileRead =
    | ({ readonly ok: true } & ReplayFileLines)
    | { readonly ok: false; readonly refusal: ReplayRefusal };

export function isReplayEvent(line: ReplayLine): line is ReplayEvent {
    return line.type in REPLAY_EVENT_TYPES;
}

export function isSeatControlLine(line: ReplayLine): line is SeatControlLine {
    return line.type in SEAT_CONTROL_LINE_TYPES;
}

/**
 * What a parsed replay line does to the table: a replay event or a seat control line, or null for a message the
 * server never records in a replay (a prompt, an error, a furiten notice, a session message).
 */
export function replayLineTableEvent(line: ReplayLine): TableEvent | null {
    return isReplayEvent(line) || isSeatControlLine(line) ? line : null;
}

interface DecodedRecords {
    readonly lines: readonly ReplayFileLine[];
    readonly failure: ReplayRecordFailure | null;
}

function readRecords(content: Uint8Array): DecodedRecords {
    const lines: ReplayFileLine[] = [];
    let lineNumber = 1;
    try {
        for (const value of decodeReplayRecords(content)) {
            lines.push({ lineNumber, raw: value });
            lineNumber += 1;
        }
    } catch (error) {
        const failure: ReplayRecordFailure =
            error instanceof RangeError
                ? { kind: "incomplete_record", record: lineNumber }
                : { cause: error, kind: "invalid_record", record: lineNumber };
        return { failure, lines };
    }
    return { failure: null, lines };
}

function recordFailureDetail(failure: ReplayRecordFailure): string {
    if (failure.kind === "incomplete_record") {
        return `Incomplete MessagePack record ${failure.record}`;
    }
    const { cause } = failure;
    return `Invalid MessagePack record ${failure.record}: ${cause instanceof Error ? cause.message : String(cause)}`;
}

function versionRefusal(records: DecodedRecords): ReplayRefusal | null {
    const [first] = records.lines;
    if (first === undefined) {
        return records.failure ?? { kind: "empty" };
    }
    const { raw } = first;
    if (!(WIRE_KEY.REPLAY_VERSION in raw) || Object.keys(raw).length !== 1) {
        return { kind: "no_version_record" };
    }
    return raw[WIRE_KEY.REPLAY_VERSION] === REPLAY_VERSION
        ? null
        : { kind: "unsupported_version", version: JSON.stringify(raw[WIRE_KEY.REPLAY_VERSION]) };
}

/** Read independent MessagePack records, retaining only the prefix before a damaged record. */
export function readReplayFile(content: Uint8Array): ReplayFileRead {
    if (content.length > MAX_REPLAY_BYTES) {
        return { ok: false, refusal: { kind: "too_large" } };
    }
    const records = readRecords(content);
    const refusal = versionRefusal(records);
    if (refusal !== null) {
        return { ok: false, refusal };
    }
    const { failure } = records;
    const errors =
        failure === null
            ? []
            : [{ detail: recordFailureDetail(failure), lineNumber: failure.record }];
    return { errors, lines: records.lines.slice(1), ok: true };
}
