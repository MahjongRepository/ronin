import { type ReplayEvent } from "@/entities/table/model/types";
import {
    REPLAY_VERSION,
    type ReplayLine,
    type SeatControlLine,
    parseReplayLine,
} from "@/shared/protocol";

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

export interface ParsedReplay {
    readonly errors: readonly string[];
    readonly events: readonly ReplayEvent[];
}

/** A replay file read whole, or refused before any event line because of its version line. */
export type ReplayParse =
    | ({ readonly ok: true } & ParsedReplay)
    | { readonly ok: false; readonly refusal: string };

type LineOutcome =
    | { readonly kind: "event"; readonly event: ReplayEvent }
    | { readonly kind: "skipped" }
    | { readonly kind: "error"; readonly error: string };

export function isReplayEvent(line: ReplayLine): line is ReplayEvent {
    return line.type in REPLAY_EVENT_TYPES;
}

function isSeatControlLine(line: ReplayLine): line is SeatControlLine {
    return line.type in SEAT_CONTROL_LINE_TYPES;
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

function findVersionRefusal(versionLine: string | undefined): string | null {
    if (versionLine === undefined) {
        return "Replay is empty";
    }
    const version = readReplayVersion(versionLine);
    if (version === undefined) {
        return "Replay does not start with a version line";
    }
    if (version !== REPLAY_VERSION) {
        return `Unsupported replay version ${JSON.stringify(version)}`;
    }
    return null;
}

function classifyLine(line: ReplayLine): LineOutcome {
    if (isReplayEvent(line)) {
        return { event: line, kind: "event" };
    }
    if (isSeatControlLine(line)) {
        return { kind: "skipped" };
    }
    return { error: `Non-replay event type: ${line.type}`, kind: "error" };
}

function parseLine(line: string): LineOutcome {
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
    const [error, parsed] = parseReplayLine(raw);
    return error ? { error: `Parse error: ${error.message}`, kind: "error" } : classifyLine(parsed);
}

function parseEventLines(lines: readonly string[]): ParsedReplay {
    const errors: string[] = [];
    const events: ReplayEvent[] = [];
    for (const line of lines) {
        const outcome = parseLine(line);
        if (outcome.kind === "event") {
            events.push(outcome.event);
        } else if (outcome.kind === "error") {
            errors.push(outcome.error);
        }
    }
    return { errors, events };
}

/**
 * Read a replay file: its version line must name the `REPLAY_VERSION` this client was built for, since another
 * version's lines may mean something else. Each later line becomes a replay event, is skipped as a replay-only
 * seat control line, or is reported as an error without stopping the rest.
 */
export function parseReplayLines(text: string): ReplayParse {
    const [versionLine, ...eventLines] = text
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
    const refusal = findVersionRefusal(versionLine);
    if (refusal !== null) {
        return { ok: false, refusal };
    }

    return { ...parseEventLines(eventLines), ok: true };
}
