import { encode } from "@msgpack/msgpack";
import { assert, describe, expect, expectTypeOf, test } from "vitest";

import { encodeReplayLines, encodeReplayRecords, joinBytes } from "#tests/fixtures/replay-records";
import { WIRE_GAME_END, WIRE_GAME_STARTED, WIRE_ROUND_STARTED } from "#tests/fixtures/wire";
import { type ReplayEvent, isReplayEvent, readReplayFile } from "@/entities/table";
import {
    type ParsedServerMessage,
    REPLAY_VERSION,
    WIRE_KEY,
    parseServerMessage,
} from "@/shared/protocol";

// eslint-disable-next-line import/no-relative-parent-imports -- Shared backend golden pins the cross-language wire contract.
import golden from "../../../../../../backend/game/tests/fixtures/replay-format-golden.json";

const VERSION_LINE = JSON.stringify({ [WIRE_KEY.REPLAY_VERSION]: REPLAY_VERSION });
const drawLine = JSON.stringify({
    [WIRE_KEY.PACKED_MOVE]: 136,
    [WIRE_KEY.EVENT_TYPE]: 1,
    [WIRE_KEY.TILES_REMAINING]: 69,
});

describe("readReplayFile - version", () => {
    test("refuses a replay of another version", () => {
        const read = readReplayFile(
            encodeReplayLines(
                `${JSON.stringify({ [WIRE_KEY.REPLAY_VERSION]: "0.2" })}\n${drawLine}`,
            ),
        );
        expect(read).toEqual({
            ok: false,
            refusal: { kind: "unsupported_version", version: '"0.2"' },
        });
    });

    test("refuses a replay that does not start with a version record", () => {
        const read = readReplayFile(encodeReplayLines(`${drawLine}\n${drawLine}`));
        expect(read).toEqual({ ok: false, refusal: { kind: "no_version_record" } });
    });

    test("refuses an empty replay", () => {
        expect(readReplayFile(new Uint8Array())).toEqual({
            ok: false,
            refusal: { kind: "empty" },
        });
    });

    test("refuses a replay whose version record does not decode, by its record number and cause", () => {
        const truncated = encodeReplayRecords([
            { [WIRE_KEY.REPLAY_VERSION]: REPLAY_VERSION },
        ]).slice(0, -1);
        expect(readReplayFile(truncated)).toEqual({
            ok: false,
            refusal: { kind: "incomplete_record", record: 1 },
        });
        const read = readReplayFile(new Uint8Array([129, 161, 49, 1]));
        assert(!read.ok && read.refusal.kind === "invalid_record");
        expect(read.refusal.record).toBe(1);
        expect(read.refusal.cause).toEqual(new Error("Unknown replay metadata key: 1"));
    });
});

describe("readReplayFile - records", () => {
    test("keeps the readable prefix and reports the first incomplete record", () => {
        const complete = encodeReplayLines([VERSION_LINE, drawLine].join("\n"));
        const partial = encodeReplayRecords([
            { [WIRE_KEY.PACKED_MOVE]: 5, [WIRE_KEY.EVENT_TYPE]: 1, [WIRE_KEY.TILES_REMAINING]: 68 },
        ]).slice(0, -1);
        const read = readReplayFile(joinBytes([complete, partial]));
        expect(read.ok && read.lines).toEqual([
            {
                lineNumber: 2,
                raw: {
                    [WIRE_KEY.PACKED_MOVE]: 136,
                    [WIRE_KEY.EVENT_TYPE]: 1,
                    [WIRE_KEY.TILES_REMAINING]: 69,
                },
            },
        ]);
        expect(read.ok && read.errors).toEqual([
            { detail: "Incomplete MessagePack record 3", lineNumber: 3 },
        ]);
    });

    test.each([
        ["string metadata", new Uint8Array([129, 161, 49, 1]), "Unknown replay metadata key: 1"],
        [
            "duplicate metadata",
            new Uint8Array([130, WIRE_KEY.EVENT_TYPE, 1, WIRE_KEY.EVENT_TYPE, 2]),
            `Duplicate replay map key: ${WIRE_KEY.EVENT_TYPE}`,
        ],
    ])("rejects %s before exposing the damaged record", (_name, record, detail) => {
        const read = readReplayFile(
            joinBytes([
                encodeReplayRecords([{ [WIRE_KEY.REPLAY_VERSION]: REPLAY_VERSION }]),
                record,
            ]),
        );
        expect(read.ok && read.errors).toEqual([
            {
                detail: `Invalid MessagePack record 2: ${detail}`,
                lineNumber: 2,
            },
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
            discard: { [WIRE_KEY.PACKED_MOVE]: 0, [WIRE_KEY.EVENT_TYPE]: 2 },
            dora_revealed: { [WIRE_KEY.EVENT_TYPE]: 6, [WIRE_KEY.TILE_ID]: 0 },
            draw: {
                [WIRE_KEY.BANK_SECONDS]: 20,
                [WIRE_KEY.PACKED_MOVE]: 136,
                [WIRE_KEY.EVENT_TYPE]: 1,
                [WIRE_KEY.TILES_REMAINING]: 69,
                [WIRE_KEY.WAIT_ID]: 1,
            },
            game_end: WIRE_GAME_END,
            game_started: WIRE_GAME_STARTED,
            meld: { [WIRE_KEY.PACKED_MELD]: 24_384, [WIRE_KEY.EVENT_TYPE]: 0 },
            riichi_declared: {
                [WIRE_KEY.RIICHI_STICKS]: 1,
                [WIRE_KEY.SEAT]: 0,
                [WIRE_KEY.SCORE]: 240,
                [WIRE_KEY.EVENT_TYPE]: 5,
            },
            round_end: {
                [WIRE_KEY.DORA_INDICATORS]: [40],
                [WIRE_KEY.DEALER]: 0,
                [WIRE_KEY.RIICHI_STICKS]: 4,
                [WIRE_KEY.ABORTIVE_REASON]: "four_riichi",
                [WIRE_KEY.RESULT_TYPE]: 4,
                [WIRE_KEY.SCORE_CHANGES]: { "0": 0, "1": 0, "2": 0, "3": 0 },
                [WIRE_KEY.SCORES]: { "0": 250, "1": 250, "2": 250, "3": 250 },
                [WIRE_KEY.EVENT_TYPE]: 4,
            },
            round_started: WIRE_ROUND_STARTED,
        };

        for (const [type, wire] of Object.entries(replayLines)) {
            const msg = parsedMessage(wire);
            expect([msg.type, isReplayEvent(msg)]).toEqual([type, true]);
        }
    });

    test("rejects error event", () => {
        const msg = parsedMessage({
            [WIRE_KEY.GAME_ERROR_CODE]: "test",
            [WIRE_KEY.GAME_ERROR_MESSAGE]: "test",
            [WIRE_KEY.EVENT_TYPE]: 7,
        });
        expect(isReplayEvent(msg)).toBe(false);
    });

    test("rejects furiten event", () => {
        const msg = parsedMessage({ [WIRE_KEY.FURITEN]: true, [WIRE_KEY.EVENT_TYPE]: 11 });
        expect(isReplayEvent(msg)).toBe(false);
    });
});

describe("readReplayFile - shared format contract", () => {
    test("restores Python golden records including seed, string overrides, score seats and ordinary tile arrays", () => {
        const content = Uint8Array.from(golden.hex.match(/../g) ?? [], (byte) =>
            Number.parseInt(byte, 16),
        );
        const read = readReplayFile(content);
        assert(read.ok);
        expectTypeOf(read.lines[0].raw).toEqualTypeOf<Readonly<Record<string, unknown>>>();
        expect(
            Object.fromEntries(
                Object.entries(WIRE_KEY).filter(([, id]) => id <= WIRE_KEY.YAKU_YAKUMAN_COUNT),
            ),
        ).toEqual(golden.named_keys);
        expect(read.errors).toEqual([]);
        expect(read.lines.map((line) => line.raw)).toEqual(golden.records.slice(1));
    });

    test.each([new Uint8Array(95), "00".repeat(96)])(
        "refuses malformed seed representation",
        (seed) => {
            const record = new Uint8Array([129, 54, ...encode(seed)]);
            const read = readReplayFile(
                joinBytes([
                    encodeReplayRecords([{ [WIRE_KEY.REPLAY_VERSION]: REPLAY_VERSION }]),
                    record,
                ]),
            );
            assert(read.ok);
            expect(read.lines).toEqual([]);
            expect(read.errors).toEqual([
                {
                    detail: "Invalid MessagePack record 2: Replay seed must contain exactly 96 binary bytes",
                    lineNumber: 2,
                },
            ]);
        },
    );
});
