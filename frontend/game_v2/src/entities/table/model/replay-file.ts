import { type ReplayEvent, type TableEvent } from "@/entities/table/model/types";
import { REPLAY_VERSION, type ReplayLine, type SeatControlLine } from "@/shared/protocol";

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

/** An event line of a replay file as a JSON object, still to be parsed, with its 1-based line number in the file. */
export interface ReplayFileLine {
    readonly lineNumber: number;
    readonly raw: Readonly<Record<string, unknown>>;
}

/** A line of a replay file that could not be read, by its 1-based line number. */
export interface ReplayLineError {
    readonly lineNumber: number;
    readonly detail: string;
}

/** A replay file's event lines as JSON objects, beside the lines that were not JSON objects. */
export interface ReplayFileLines {
    readonly lines: readonly ReplayFileLine[];
    readonly errors: readonly ReplayLineError[];
}

interface NumberedText {
    readonly lineNumber: number;
    readonly text: string;
}

/**
 * Why a replay file is refused before any event line: it holds no version line this client can read, or one naming
 * another version, whose lines may mean something else.
 */
export type ReplayRefusal =
    | { readonly kind: "unreadable"; readonly detail: string }
    | { readonly kind: "unsupported_version"; readonly version: string };

/** A replay file read whole, or refused before any event line because of its version line. */
export type ReplayFileRead =
    | ({ readonly ok: true } & ReplayFileLines)
    | { readonly ok: false; readonly refusal: ReplayRefusal };

type LineRead =
    | { readonly kind: "line"; readonly line: Record<string, unknown> }
    | { readonly kind: "error"; readonly error: string };

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

function isJsonObject(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readReplayVersion(line: string): unknown {
    try {
        const raw: unknown = JSON.parse(line);
        return isJsonObject(raw) ? raw.version : undefined;
    } catch {
        return undefined;
    }
}

function findVersionRefusal(versionLine: string | undefined): ReplayRefusal | null {
    if (versionLine === undefined) {
        return { detail: "The replay is empty", kind: "unreadable" };
    }
    const version = readReplayVersion(versionLine);
    if (version === undefined) {
        return { detail: "The replay does not start with a version line", kind: "unreadable" };
    }
    if (version !== REPLAY_VERSION) {
        return { kind: "unsupported_version", version: JSON.stringify(version) };
    }
    return null;
}

function readLine(line: string): LineRead {
    let raw: unknown = null;
    try {
        raw = JSON.parse(line);
    } catch (parseError) {
        const detail = parseError instanceof Error ? parseError.message : String(parseError);
        return { error: `JSON parse error: ${detail}`, kind: "error" };
    }
    if (!isJsonObject(raw)) {
        return { error: "Parse error: line is not a JSON object", kind: "error" };
    }
    return { kind: "line", line: raw };
}

function readEventLines(texts: readonly NumberedText[]): ReplayFileLines {
    const errors: ReplayLineError[] = [];
    const lines: ReplayFileLine[] = [];
    for (const { lineNumber, text } of texts) {
        const read = readLine(text);
        if (read.kind === "line") {
            lines.push({ lineNumber, raw: read.line });
        } else {
            errors.push({ detail: read.error, lineNumber });
        }
    }
    return { errors, lines };
}

/**
 * Read a replay file: its version line must name the `REPLAY_VERSION` this client was built for, since another
 * version's lines may mean something else. Each later line becomes a JSON object for the client to parse as a
 * replay line, or is reported as an error without stopping the rest.
 */
export function readReplayFile(text: string): ReplayFileRead {
    const [versionLine, ...eventLines] = text
        .split("\n")
        .map((line, index) => ({ lineNumber: index + 1, text: line.trim() }))
        .filter((line) => line.text !== "");
    const refusal = findVersionRefusal(versionLine?.text);
    if (refusal !== null) {
        return { ok: false, refusal };
    }
    return { ...readEventLines(eventLines), ok: true };
}
