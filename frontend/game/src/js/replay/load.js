import wire from "../ronin/wire.js";

const HTTP_NOT_FOUND = 404;

export const REPLAY_ERROR = Object.freeze({
    NOT_FOUND: "not_found",
    FAILED: "failed",
    VERSION: "version",
    MALFORMED: "malformed",
});

function failure(kind) {
    return { error: { kind } };
}

function malformed(line) {
    const kind = REPLAY_ERROR.MALFORMED;
    return { error: line === undefined ? { kind } : { kind, line } };
}

function parseRecord(text) {
    try {
        const value = JSON.parse(text);
        return typeof value === "object" && value !== null && !Array.isArray(value) ? value : null;
    } catch {
        return null;
    }
}

function numberedLines(text) {
    return text
        .split("\n")
        .map((line, index) => ({ text: line, number: index + 1 }))
        .filter((line) => line.text.trim() !== "");
}

/**
 * Parse a replay file into its event lines, game_started first: `{ lines, lineNumbers }`, where
 * `lineNumbers[i]` is the 1-based file line of `lines[i]`, or `{ error: { kind, line? } }`, where
 * `line` is the file line a malformed replay breaks at.
 */
export function parseReplay(text) {
    const [versionLine, ...eventLines] = numberedLines(text);
    if (versionLine === undefined) {
        return malformed();
    }
    const tag = parseRecord(versionLine.text);
    if (typeof tag?.version !== "string") {
        return malformed(versionLine.number);
    }
    if (tag.version !== wire.REPLAY_VERSION) {
        return failure(REPLAY_ERROR.VERSION);
    }
    if (eventLines.length === 0) {
        return malformed();
    }
    const lines = [];
    for (const line of eventLines) {
        const record = parseRecord(line.text);
        if (record === null) {
            return malformed(line.number);
        }
        lines.push(record);
    }
    if (lines[0].t !== wire.E.GAME_STARTED) {
        return malformed(eventLines[0].number);
    }
    return { lines, lineNumbers: eventLines.map((line) => line.number) };
}

async function fetchReplayText(gameId) {
    try {
        const response = await fetch(`/api/replays/${encodeURIComponent(gameId)}`);
        if (response.status === HTTP_NOT_FOUND) {
            return failure(REPLAY_ERROR.NOT_FOUND);
        }
        if (!response.ok) {
            return failure(REPLAY_ERROR.FAILED);
        }
        return { text: await response.text() };
    } catch {
        return failure(REPLAY_ERROR.FAILED);
    }
}

/** Fetch a game's replay and parse it, as `parseReplay` does. */
export async function loadReplay(gameId) {
    const fetched = await fetchReplayText(gameId);
    return fetched.error ? fetched : parseReplay(fetched.text);
}
