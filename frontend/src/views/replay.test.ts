import { isAbortError, isVersionTag, parseReplayLines } from "@/views/replay";
import { describe, expect, test } from "vitest";

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
const drawLine = '{"t": 1, "d": 136}';
// discard: t=2, d=0 (seat 0, tile 0, no flags)
const discardLine = '{"t": 2, "d": 0}';
// meld: t=0, m=24384 (ankan)
const meldLine = '{"t": 0, "m": 24384}';

describe("parseReplayLines - line filtering", () => {
    test("skips version tag on first line", () => {
        const text = `{"version": "1.0"}\n${drawLine}\n${discardLine}`;
        const result = parseReplayLines(text);
        expect(result).toHaveLength(2);
        expect(result[0].type).toBe("draw");
        expect(result[1].type).toBe("discard");
    });

    test("keeps first line when it is not a version tag", () => {
        const text = `${meldLine}\n${drawLine}`;
        const result = parseReplayLines(text);
        expect(result).toHaveLength(2);
        expect(result[0].type).toBe("meld");
    });

    test("filters empty and whitespace-only lines", () => {
        const text = `${drawLine}\n\n   \n${discardLine}\n`;
        const result = parseReplayLines(text);
        expect(result).toHaveLength(2);
    });

    test("returns empty array for empty input", () => {
        expect(parseReplayLines("")).toHaveLength(0);
    });

    test("version tag on second line is not skipped", () => {
        const text = `${drawLine}\n{"version": "1.0"}`;
        const result = parseReplayLines(text);
        expect(result).toHaveLength(2);
        expect(result[1].type).toBe("unknown");
    });
});

describe("parseReplayLines - parsing", () => {
    test("parsed output contains camelCase fields", () => {
        const text = drawLine;
        const result = parseReplayLines(text);
        const parsed = JSON.parse(result[0].raw);
        expect(parsed.type).toBe("draw");
        expect(parsed.seat).toBe(1);
        expect(parsed.tileId).toBe(0);
    });

    test("falls back to raw line for unparseable JSON", () => {
        const text = "not json";
        const result = parseReplayLines(text);
        expect(result[0].raw).toContain("not json");
        expect(result[0].raw).toContain("[JSON parse error:");
        expect(result[0].type).toBe("unknown");
    });

    test("falls back for unknown event type", () => {
        const text = '{"t": 99}';
        const result = parseReplayLines(text);
        expect(result[0].raw).toContain('{"t": 99}');
        expect(result[0].raw).toContain("[Parse error:");
        expect(result[0].type).toBe("unknown");
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
