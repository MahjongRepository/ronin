import { extractEventType, isAbortError, isVersionTag, parseReplayLines } from "@/views/replay";
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

describe("extractEventType", () => {
    test("extracts numeric event type", () => {
        expect(extractEventType('{"t": 4}')).toBe("4");
    });

    test("extracts string event type", () => {
        expect(extractEventType('{"t": "round_end"}')).toBe("round_end");
    });

    test("returns 'unknown' when .t field is missing", () => {
        expect(extractEventType('{"data": {}}')).toBe("unknown");
    });

    test("returns 'unknown' for invalid JSON", () => {
        expect(extractEventType("{broken")).toBe("unknown");
    });
});

describe("parseReplayLines", () => {
    test("skips version tag on first line", () => {
        const text = '{"version": "1.0"}\n{"t": 1}\n{"t": 2}';
        const result = parseReplayLines(text);
        expect(result).toHaveLength(2);
        expect(result[0].type).toBe("1");
        expect(result[1].type).toBe("2");
    });

    test("keeps first line when it is not a version tag", () => {
        const text = '{"t": 0}\n{"t": 1}';
        const result = parseReplayLines(text);
        expect(result).toHaveLength(2);
        expect(result[0].type).toBe("0");
    });

    test("filters empty and whitespace-only lines", () => {
        const text = '{"t": 1}\n\n   \n{"t": 2}\n';
        const result = parseReplayLines(text);
        expect(result).toHaveLength(2);
    });

    test("trims whitespace from raw lines", () => {
        const text = '  {"t": 1}  ';
        const result = parseReplayLines(text);
        expect(result[0].raw).toBe('{"t": 1}');
    });

    test("returns empty array for empty input", () => {
        expect(parseReplayLines("")).toHaveLength(0);
    });

    test("version tag on second line is not skipped", () => {
        const text = '{"t": 0}\n{"version": "1.0"}';
        const result = parseReplayLines(text);
        expect(result).toHaveLength(2);
        expect(result[1].raw).toBe('{"version": "1.0"}');
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
