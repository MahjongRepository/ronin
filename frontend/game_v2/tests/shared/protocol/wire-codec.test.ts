import { encode } from "@msgpack/msgpack";
import { describe, expect, expectTypeOf, it } from "vitest";

import { joinBytes } from "#tests/fixtures/replay-records";
import { WIRE_KEY, decodeWireMessage, encodeWireMessage } from "@/shared/protocol";
import { MAX_WIRE_BYTES } from "@/shared/protocol/wire-codec";

// eslint-disable-next-line import/no-relative-parent-imports -- Shared backend golden pins the cross-language wire contract.
import golden from "../../../../../backend/game/tests/fixtures/live-protocol-golden.json";

function fromHex(hex: string): Uint8Array<ArrayBuffer> {
    return Uint8Array.from(hex.match(/../g) ?? [], (byte) => Number.parseInt(byte, 16));
}

describe("live protocol codec", () => {
    it("uses the Python field IDs and restores all golden messages, nested metadata and score-seat keys", () => {
        expect(WIRE_KEY).toMatchObject(golden.named_keys);
        for (const frame of golden.frames) {
            const decoded = decodeWireMessage(fromHex(frame.hex));
            expect(decoded, frame.name).toEqual(frame.payload);
            expect(decodeWireMessage(encodeWireMessage(frame.payload)), frame.name).toEqual(
                frame.payload,
            );
            expectTypeOf(decoded).toEqualTypeOf<Record<string, unknown>>();
        }
    });

    it.each([
        ["string metadata key", encode({ t: 1 })],
        ["unknown metadata key", new Uint8Array([129, 127, 1])],
        [
            "duplicate metadata",
            new Uint8Array([130, WIRE_KEY.EVENT_TYPE, 1, WIRE_KEY.EVENT_TYPE, 2]),
        ],
        ["boolean key", new Uint8Array([129, 195, 1])],
        ["integer seat key", new Uint8Array([129, WIRE_KEY.SCORES, 129, 0, 1])],
        ["noninteger score", new Uint8Array([129, WIRE_KEY.SCORES, 129, 161, 48, 195])],
        [
            "duplicate seat",
            joinBytes([
                new Uint8Array([129, WIRE_KEY.SCORES, 130]),
                encode("0"),
                encode(250),
                encode("0"),
                encode(240),
            ]),
        ],
        ["non-object message", encode([1, 2])],
        ["truncated message", new Uint8Array([129, WIRE_KEY.EVENT_TYPE])],
        ["replay-only key", new Uint8Array([129, WIRE_KEY.REPLAY_VERSION, 1])],
    ])("rejects %s before exposing a message", (_name, content) => {
        expect(() => decodeWireMessage(content)).toThrow();
    });

    it("rejects excessive frame size and nesting", () => {
        expect(() => decodeWireMessage(new Uint8Array(MAX_WIRE_BYTES + 1))).toThrow("size limit");
        const nested = new Uint8Array([
            ...Array.from({ length: 34 }, () => [129, WIRE_KEY.ROUND_RESULT]).flat(),
            192,
        ]);
        expect(() => decodeWireMessage(nested)).toThrow("nesting limit");
    });

    it("refuses unknown outgoing fields instead of writing string metadata", () => {
        expect(() => encodeWireMessage({ unexpected: 1 })).toThrow("Unknown protocol field");
    });
});
