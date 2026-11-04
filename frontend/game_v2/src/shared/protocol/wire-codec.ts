import { Decoder, encode } from "@msgpack/msgpack";

import { LIVE_WIRE_KEYS, WIRE_KEY } from "./wire-keys.ts";

export const MAX_WIRE_BYTES = 256 * 1024;
const MAX_STRING_BYTES = 64 * 1024;
const MAX_BINARY_BYTES = 64 * 1024;
const MAX_ARRAY_LENGTH = 1024;
const MAX_MAP_LENGTH = 256;
const MAX_DEPTH = 32;
const FIXED_COLLECTION_LIMIT = 16;
const FIXMAP = 128;
const FIXARRAY = 144;
const MAP16 = 222;
const ARRAY16 = 220;
const SCORE_KEYS: ReadonlySet<number> = new Set([WIRE_KEY.SCORES, WIRE_KEY.SCORE_CHANGES]);
const SEAT_KEYS: ReadonlySet<string> = new Set(["0", "1", "2", "3"]);

function isRecord(value: unknown): value is Record<string, unknown> {
    return (
        typeof value === "object" &&
        value !== null &&
        Object.getPrototypeOf(value) === Object.prototype
    );
}

function joinBytes(parts: readonly Uint8Array[]): Uint8Array<ArrayBuffer> {
    const length = parts.reduce((total, part) => total + part.length, 0);
    if (length > MAX_WIRE_BYTES) {
        throw new Error("Protocol frame exceeds the size limit");
    }
    const joined = new Uint8Array(length);
    let offset = 0;
    for (const part of parts) {
        joined.set(part, offset);
        offset += part.length;
    }
    return joined;
}

function collectionHeader(length: number, map: boolean): Uint8Array {
    if (length > (map ? MAX_MAP_LENGTH : MAX_ARRAY_LENGTH)) {
        throw new Error("Protocol collection exceeds the size limit");
    }
    return length < FIXED_COLLECTION_LIMIT
        ? new Uint8Array([(map ? FIXMAP : FIXARRAY) + length])
        : new Uint8Array([map ? MAP16 : ARRAY16, length >> 8, length & 255]);
}

function encodeValue(value: unknown, depth: number, scoreMap = false): Uint8Array {
    if (depth > MAX_DEPTH) {
        throw new Error("Protocol nesting limit exceeded");
    }
    if (scoreMap && !isRecord(value)) {
        throw new Error("Protocol score map must be an object");
    }
    if (Array.isArray(value)) {
        return joinBytes([
            collectionHeader(value.length, false),
            ...value.map((entry: unknown) => encodeValue(entry, depth + 1)),
        ]);
    }
    if (!isRecord(value)) {
        return encode(value);
    }
    const entries = Object.entries(value);
    return joinBytes([
        collectionHeader(entries.length, true),
        ...entries.flatMap(([name, entry]) => {
            if (scoreMap) {
                if (!SEAT_KEYS.has(name) || !Number.isSafeInteger(entry)) {
                    throw new Error(
                        "Protocol score maps require string seat keys and integer scores",
                    );
                }
                return [encode(name), encode(entry)];
            }
            const id = Number(name);
            if (String(id) !== name || !LIVE_WIRE_KEYS.has(id)) {
                throw new Error(`Unknown protocol field: ${name}`);
            }
            return [encode(id), encodeValue(entry, depth + 1, SCORE_KEYS.has(id))];
        }),
    ]);
}

export function encodeWireMessage(
    message: Readonly<Record<string, unknown>>,
): Uint8Array<ArrayBuffer> {
    return joinBytes([encodeValue(message, 0)]);
}

interface DecodeContext {
    readonly keys: readonly (number | string)[];
    readonly depth: number;
    readonly scoreMap: boolean;
}

function validateMapKey(key: number | string, scoreMap: boolean): number | string {
    if (scoreMap && typeof key === "string" && SEAT_KEYS.has(key)) {
        return key;
    }
    if (!scoreMap && typeof key === "number" && LIVE_WIRE_KEYS.has(key)) {
        return key;
    }
    throw new Error("Unknown or invalid protocol map key");
}

function validateScore(value: unknown): void {
    if (!Number.isSafeInteger(value)) {
        throw new Error("Protocol score maps require integer scores");
    }
}

function restoreMap(
    value: Record<string, unknown>,
    context: DecodeContext,
): Record<string, unknown> {
    const restored: Record<string, unknown> = {};
    for (const [placeholder, entry] of Object.entries(value)) {
        const key = context.keys[Number(placeholder)];
        const name = validateMapKey(key, context.scoreMap);
        if (Object.hasOwn(restored, name)) {
            throw new Error(`Duplicate protocol field: ${name}`);
        }
        if (context.scoreMap) {
            validateScore(entry);
        }
        restored[name] = restoreValue(entry, {
            depth: context.depth + 1,
            keys: context.keys,
            scoreMap: typeof key === "number" && SCORE_KEYS.has(key),
        });
    }
    return restored;
}

function restoreValue(value: unknown, context: DecodeContext): unknown {
    if (context.depth > MAX_DEPTH) {
        throw new Error("Protocol nesting limit exceeded");
    }
    if (context.scoreMap && !isRecord(value)) {
        throw new Error("Protocol score map must be an object");
    }
    if (Array.isArray(value)) {
        return value.map((entry: unknown) =>
            restoreValue(entry, { ...context, depth: context.depth + 1 }),
        );
    }
    return isRecord(value) ? restoreMap(value, context) : value;
}

export function decodeWireMessage(content: Uint8Array): Record<string, unknown> {
    if (content.length > MAX_WIRE_BYTES) {
        throw new Error("Protocol frame exceeds the size limit");
    }
    const keys: (number | string)[] = [];
    const decoder = new Decoder({
        mapKeyConverter(key: unknown): string {
            if (
                typeof key !== "string" &&
                !(typeof key === "number" && Number.isSafeInteger(key))
            ) {
                throw new Error("Invalid protocol map key");
            }
            keys.push(key);
            return String(keys.length - 1);
        },
        maxArrayLength: MAX_ARRAY_LENGTH,
        maxBinLength: MAX_BINARY_BYTES,
        maxExtLength: 0,
        maxMapLength: MAX_MAP_LENGTH,
        maxStrLength: MAX_STRING_BYTES,
    });
    const restored = restoreValue(decoder.decode(content), { depth: 0, keys, scoreMap: false });
    if (!isRecord(restored)) {
        throw new Error("Protocol frame must be a message object");
    }
    return restored;
}
