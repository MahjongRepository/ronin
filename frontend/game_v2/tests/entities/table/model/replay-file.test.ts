import { assert, describe, expect, test } from "vitest";

import { ENGINE_REPLAYS } from "#tests/fixtures/replays";
import { WIRE_GAME_END, WIRE_GAME_STARTED } from "#tests/fixtures/wire";
import {
    type BoardDisplayState,
    type ParsedReplay,
    type ReplayEvent,
    buildActionSteps,
    buildNavigationIndex,
    buildTimeline,
    isReplayEvent,
    parseReplayLines,
    tableStateToDisplayState,
} from "@/entities/table";
import { type ParsedServerMessage, REPLAY_VERSION, parseServerMessage } from "@/shared/protocol";

const VERSION_LINE = JSON.stringify({ version: REPLAY_VERSION });

function parseEventLines(...lines: string[]): ParsedReplay {
    const parsed = parseReplayLines([VERSION_LINE, ...lines].join("\n"));
    if (!parsed.ok) {
        throw new Error(parsed.refusal);
    }
    return parsed;
}

const drawLine = '{"d": 136, "t": 1}';
const discardLine = '{"d": 0, "t": 2}';
const meldLine = '{"m": 24384, "t": 0}';

describe("parseReplayLines - version", () => {
    test("refuses a replay of another version", () => {
        const parsed = parseReplayLines(`{"version": "0.2"}\n${drawLine}`);
        expect(parsed).toEqual({ ok: false, refusal: 'Unsupported replay version "0.2"' });
    });

    test("refuses a replay that does not start with a version line", () => {
        const parsed = parseReplayLines(`${meldLine}\n${drawLine}`);
        expect(parsed).toEqual({ ok: false, refusal: "Replay does not start with a version line" });
    });

    test("refuses an empty replay", () => {
        expect(parseReplayLines(" \n")).toEqual({ ok: false, refusal: "Replay is empty" });
    });
});

describe("parseReplayLines - line filtering", () => {
    test("parses the events after the version line", () => {
        const { errors, events } = parseEventLines(meldLine, drawLine, discardLine);
        expect(errors).toEqual([]);
        expect(events.map((event) => event.type)).toEqual(["meld", "draw", "discard"]);
    });

    test("filters empty and whitespace-only lines", () => {
        const { events } = parseEventLines(drawLine, "", "   ", discardLine, "");
        expect(events).toHaveLength(2);
    });

    test("version tag on second line surfaces as error", () => {
        const { errors, events } = parseEventLines(drawLine, VERSION_LINE);
        expect(events).toHaveLength(1);
        expect(errors).toHaveLength(1);
        expect(errors[0]).toContain("Parse error:");
    });
});

describe("parseReplayLines - event parsing", () => {
    test("parsed events have correct types and fields", () => {
        const { events } = parseEventLines(drawLine);
        expect(events[0].type).toBe("draw");
        expect(events[0]).toHaveProperty("seat", 1);
        expect(events[0]).toHaveProperty("tileId", 0);
    });

    test("malformed JSON surfaces in errors", () => {
        const { errors, events } = parseEventLines("not json");
        expect(events).toHaveLength(0);
        expect(errors).toHaveLength(1);
        expect(errors[0]).toContain("JSON parse error:");
    });

    test("unknown event type surfaces in errors", () => {
        const { errors, events } = parseEventLines('{"t": 99}');
        expect(events).toHaveLength(0);
        expect(errors).toHaveLength(1);
        expect(errors[0]).toContain("Parse error:");
    });

    test("non-replay event type surfaces in errors", () => {
        const errorLine = '{"cd": "test_code", "msg": "test message", "t": 7}';
        const { errors, events } = parseEventLines(errorLine);
        expect(events).toHaveLength(0);
        expect(errors).toHaveLength(1);
        expect(errors[0]).toContain("Non-replay event type: error");
    });

    test("mixed valid and invalid lines separates correctly", () => {
        const { errors, events } = parseEventLines(drawLine, "not json", discardLine, '{"t": 99}');
        expect(events).toHaveLength(2);
        expect(errors).toHaveLength(2);
    });

    test("reads seat control lines without error, and rejects an unknown one", () => {
        const { errors, events } = parseEventLines(
            '{"ai": 1, "r": 0, "s": 2, "t": 101}',
            '{"ai": 0, "s": 2, "t": 101}',
            '{"ai": 2, "s": 2, "t": 101}',
            drawLine,
        );
        expect(events.map((event) => event.type)).toEqual(["draw"]);
        expect(errors).toEqual([
            "Parse error: Failed to parse replay line t=101: Unknown seat control: ai=2",
        ]);
    });
});

function buildBoards(events: readonly ReplayEvent[]): (BoardDisplayState | null)[] {
    const states = buildTimeline(events);
    const steps = buildActionSteps(events);
    buildNavigationIndex(events, steps, states);
    return steps.map((step) => tableStateToDisplayState(states[step.stateIndex]));
}

describe("parseReplayLines - engine fixtures", () => {
    test("loads every replay the engine records and maps each of its steps to a board", () => {
        expect(ENGINE_REPLAYS.size).toBeGreaterThan(0);
        for (const [name, text] of ENGINE_REPLAYS) {
            const parsed = parseReplayLines(text);
            expect(parsed.ok ? parsed.errors : [parsed.refusal], name).toEqual([]);
            assert(parsed.ok);
            expect(parsed.events.length, name).toBeGreaterThan(0);

            const boards = buildBoards(parsed.events);
            expect(boards.length, name).toBeGreaterThan(1);
            expect(boards.indexOf(null), name).toBe(-1);
        }
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
            draw: { d: 136, t: 1 },
            game_end: WIRE_GAME_END,
            game_started: WIRE_GAME_STARTED,
            meld: { m: 24_384, t: 0 },
            riichi_declared: { s: 0, t: 5 },
            round_end: { rn: "four_riichi", rt: 4, sch: {}, scs: { "0": 250 }, t: 4 },
            round_started: {
                cp: 0,
                di: [0],
                dl: 0,
                h: 0,
                n: 1,
                p: [{ s: 0, sc: 250 }],
                r: 0,
                t: 9,
                w: 0,
            },
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
