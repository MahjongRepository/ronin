import { describe, expect, test } from "vitest";

import { WIRE_GAME_END, WIRE_GAME_STARTED, WIRE_ROUND_STARTED } from "#tests/fixtures/wire";
import { type ReplayEvent, isReplayEvent, readReplayFile } from "@/entities/table";
import { type ParsedServerMessage, REPLAY_VERSION, parseServerMessage } from "@/shared/protocol";

const VERSION_LINE = JSON.stringify({ version: REPLAY_VERSION });
const drawLine = '{"d": 136, "t": 1, "tr": 69}';

describe("readReplayFile - version", () => {
    test("refuses a replay of another version", () => {
        const read = readReplayFile(`{"version": "0.2"}\n${drawLine}`);
        expect(read).toEqual({
            ok: false,
            refusal: { kind: "unsupported_version", version: '"0.2"' },
        });
    });

    test("refuses a replay that does not start with a version line", () => {
        const read = readReplayFile(`${drawLine}\n${drawLine}`);
        expect(read).toEqual({
            ok: false,
            refusal: {
                detail: "The replay does not start with a version line",
                kind: "unreadable",
            },
        });
    });

    test("refuses an empty replay", () => {
        expect(readReplayFile(" \n")).toEqual({
            ok: false,
            refusal: { detail: "The replay is empty", kind: "unreadable" },
        });
    });
});

describe("readReplayFile - lines", () => {
    test("reads each non-blank line after the version as a JSON object and reports one that is not", () => {
        const read = readReplayFile(
            [VERSION_LINE, drawLine, "", "  ", "not json", "[1]"].join("\n"),
        );
        expect(read.ok && read.lines).toEqual([{ lineNumber: 2, raw: { d: 136, t: 1, tr: 69 } }]);
        expect(read.ok && read.errors).toEqual([
            { detail: expect.stringContaining("JSON parse error:"), lineNumber: 5 },
            { detail: "Parse error: line is not a JSON object", lineNumber: 6 },
        ]);
    });
});

function parsedMessage(wirePayload: Record<string, unknown>): ParsedServerMessage {
    const [, msg] = parseServerMessage(wirePayload);
    if (!msg) {
        throw new Error("Failed to parse test message");
    }
    return msg;
}

describe("isReplayEvent", () => {
    test("accepts all 9 replay event types", () => {
        const replayLines: Record<ReplayEvent["type"], Record<string, unknown>> = {
            discard: { d: 0, t: 2 },
            dora_revealed: { t: 6, ti: 0 },
            draw: { bk: 20, d: 136, t: 1, tr: 69, wi: 1 },
            game_end: WIRE_GAME_END,
            game_started: WIRE_GAME_STARTED,
            meld: { m: 24_384, t: 0 },
            riichi_declared: { r: 1, s: 0, sc: 240, t: 5 },
            round_end: {
                di: [40],
                dl: 0,
                r: 4,
                rn: "four_riichi",
                rt: 4,
                sch: { "0": 0, "1": 0, "2": 0, "3": 0 },
                scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
                t: 4,
            },
            round_started: WIRE_ROUND_STARTED,
        };

        for (const [type, wire] of Object.entries(replayLines)) {
            const msg = parsedMessage(wire);
            expect([msg.type, isReplayEvent(msg)]).toEqual([type, true]);
        }
    });

    test("rejects error event", () => {
        const msg = parsedMessage({ cd: "test", msg: "test", t: 7 });
        expect(isReplayEvent(msg)).toBe(false);
    });

    test("rejects furiten event", () => {
        const msg = parsedMessage({ f: true, t: 11 });
        expect(isReplayEvent(msg)).toBe(false);
    });
});
