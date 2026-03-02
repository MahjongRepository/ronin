import { describe, expect, test } from "vitest";

import { type ParsedServerMessage, parseServerMessage } from "@/shared/protocol";
import { isAbortError, isReplayEvent, isVersionTag, parseReplayLines } from "@/views/replay";

describe("isVersionTag", () => {
    test("detects version field", () => {
        expect(isVersionTag('{"version": "1.0"}')).toBe(true);
    });

    test("rejects regular event line", () => {
        expect(isVersionTag('{"t": 1, "data": {}}')).toBe(false);
    });

    test("rejects invalid JSON", () => {
        expect(isVersionTag("not json")).toBe(false);
    });

    test("rejects version with falsy value", () => {
        expect(isVersionTag('{"version": 0}')).toBe(false);
        expect(isVersionTag('{"version": ""}')).toBe(false);
    });
});

// Realistic wire payloads for testing
// draw: t=1, d=136 (seat 1, tile 0)
const drawLine = '{"d": 136, "t": 1}';
// discard: t=2, d=0 (seat 0, tile 0, no flags)
const discardLine = '{"d": 0, "t": 2}';
// meld: t=0, m=24384 (ankan)
const meldLine = '{"m": 24384, "t": 0}';

describe("parseReplayLines - line filtering", () => {
    test("skips version tag on first line", () => {
        const text = `{"version": "1.0"}\n${drawLine}\n${discardLine}`;
        const { events } = parseReplayLines(text);
        expect(events).toHaveLength(2);
        expect(events[0].type).toBe("draw");
        expect(events[1].type).toBe("discard");
    });

    test("keeps first line when it is not a version tag", () => {
        const text = `${meldLine}\n${drawLine}`;
        const { events } = parseReplayLines(text);
        expect(events).toHaveLength(2);
        expect(events[0].type).toBe("meld");
    });

    test("filters empty and whitespace-only lines", () => {
        const text = `${drawLine}\n\n   \n${discardLine}\n`;
        const { events } = parseReplayLines(text);
        expect(events).toHaveLength(2);
    });

    test("returns empty arrays for empty input", () => {
        const { errors, events } = parseReplayLines("");
        expect(events).toHaveLength(0);
        expect(errors).toHaveLength(0);
    });

    test("version tag on second line surfaces as error", () => {
        const text = `${drawLine}\n{"version": "1.0"}`;
        const { errors, events } = parseReplayLines(text);
        expect(events).toHaveLength(1);
        expect(events[0].type).toBe("draw");
        expect(errors).toHaveLength(1);
        expect(errors[0]).toContain("Parse error:");
    });
});

describe("parseReplayLines - event parsing", () => {
    test("parsed events have correct types and fields", () => {
        const { events } = parseReplayLines(drawLine);
        expect(events[0].type).toBe("draw");
        expect(events[0]).toHaveProperty("seat", 1);
        expect(events[0]).toHaveProperty("tileId", 0);
    });

    test("malformed JSON surfaces in errors", () => {
        const text = "not json";
        const { errors, events } = parseReplayLines(text);
        expect(events).toHaveLength(0);
        expect(errors).toHaveLength(1);
        expect(errors[0]).toContain("JSON parse error:");
    });

    test("unknown event type surfaces in errors", () => {
        const text = '{"t": 99}';
        const { errors, events } = parseReplayLines(text);
        expect(events).toHaveLength(0);
        expect(errors).toHaveLength(1);
        expect(errors[0]).toContain("Parse error:");
    });

    test("non-replay event type surfaces in errors", () => {
        // error event: t=7
        const errorLine = '{"cd": "test_code", "msg": "test message", "t": 7}';
        const { errors, events } = parseReplayLines(errorLine);
        expect(events).toHaveLength(0);
        expect(errors).toHaveLength(1);
        expect(errors[0]).toContain("Non-replay event type: error");
    });

    test("mixed valid and invalid lines separates correctly", () => {
        const text = `${drawLine}\nnot json\n${discardLine}\n{"t": 99}`;
        const { errors, events } = parseReplayLines(text);
        expect(events).toHaveLength(2);
        expect(errors).toHaveLength(2);
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
        const replayTypes = [
            { d: 136, t: 1 }, // draw
            { d: 0, t: 2 }, // discard
            { m: 24384, t: 0 }, // meld
            { s: 0, t: 5 }, // riichi_declared
            { t: 6, ti: 0 }, // dora_revealed
            // game_started
            {
                dd: [
                    [1, 1],
                    [1, 1],
                ],
                dl: 0,
                gid: "g1",
                p: [{ ai: 0, nm: "P0", s: 0 }],
                t: 8,
            },
            // round_started
            { cp: 0, di: [0], dl: 0, h: 0, n: 1, p: [{ s: 0, sc: 250 }], r: 0, t: 9, w: 0 },
            // round_end (abortive draw - minimal variant)
            { rn: "four_riichi", rt: 4, sch: {}, scs: { "0": 250 }, t: 4 },
            // game_end
            { st: [{ fs: 0, s: 0, sc: 250 }], t: 10, ws: 0 },
        ];

        for (const wire of replayTypes) {
            const msg = parsedMessage(wire);
            expect(isReplayEvent(msg)).toBe(true);
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

describe("isAbortError", () => {
    test("true for DOMException with name AbortError", () => {
        expect(isAbortError(new DOMException("aborted", "AbortError"))).toBe(true);
    });

    test("false for DOMException with different name", () => {
        expect(isAbortError(new DOMException("timeout", "TimeoutError"))).toBe(false);
    });

    test("false for regular Error", () => {
        expect(isAbortError(new Error("aborted"))).toBe(false);
    });

    test("false for non-error values", () => {
        expect(isAbortError(null)).toBe(false);
        expect(isAbortError("AbortError")).toBe(false);
    });
});
