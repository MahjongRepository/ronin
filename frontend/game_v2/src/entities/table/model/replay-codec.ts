import { Decoder } from "@msgpack/msgpack";

import { REPLAY_WIRE_KEYS, WIRE_KEY } from "@/shared/protocol";

export const MAX_REPLAY_BYTES = 16 * 1024 * 1024;
const SEED_BYTES = 96;
const MAX_DEPTH = 32;

interface DecodeContext {
    readonly keys: readonly (number | string)[];
    readonly depth: number;
    readonly stringKeys: boolean;
}

function isObject(value: unknown): value is Record<string, unknown> {
    return (
        typeof value === "object" &&
        value !== null &&
        Object.getPrototypeOf(value) === Object.prototype
    );
}

function restoreSeed(value: unknown): string {
    if (!(value instanceof Uint8Array) || value.length !== SEED_BYTES) {
        throw new Error("Replay seed must contain exactly 96 binary bytes");
    }
    return Array.from(value, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function validateKey(key: number | string, stringKeys: boolean): number | string {
    if (
        stringKeys ? typeof key === "string" : typeof key === "number" && REPLAY_WIRE_KEYS.has(key)
    ) {
        return key;
    }
    throw new Error(`Unknown replay metadata key: ${key}`);
}

function restoreMap(
    value: Record<string, unknown>,
    context: DecodeContext,
): Record<string, unknown> {
    const entries: [number | string, unknown][] = [];
    const seen = new Set<number | string>();
    for (const [placeholder, entry] of Object.entries(value)) {
        const key = validateKey(context.keys[Number(placeholder)], context.stringKeys);
        if (seen.has(key)) {
            throw new Error(`Duplicate replay map key: ${key}`);
        }
        seen.add(key);
        const restored =
            key === WIRE_KEY.SEED && !context.stringKeys
                ? restoreSeed(entry)
                : restoreData(entry, {
                      depth: context.depth + 1,
                      keys: context.keys,
                      stringKeys:
                          context.stringKeys ||
                          key === WIRE_KEY.GAME_SETTINGS ||
                          key === WIRE_KEY.SCORES ||
                          key === WIRE_KEY.SCORE_CHANGES,
                  });
        entries.push([key, restored]);
    }
    return Object.fromEntries(entries);
}

function restoreData(value: unknown, context: DecodeContext): unknown {
    if (context.depth > MAX_DEPTH) {
        throw new Error("Replay nesting limit exceeded");
    }
    if (Array.isArray(value)) {
        return value.map((entry: unknown) =>
            restoreData(entry, { ...context, depth: context.depth + 1 }),
        );
    }
    if (value instanceof Uint8Array) {
        throw new Error("Only the replay seed may contain binary bytes");
    }
    return isObject(value) ? restoreMap(value, context) : value;
}

export function* decodeReplayRecords(content: Uint8Array): Generator<Record<string, unknown>> {
    const keys: (number | string)[] = [];
    const decoder = new Decoder({
        mapKeyConverter(key: unknown): string {
            if (
                typeof key !== "string" &&
                !(typeof key === "number" && Number.isSafeInteger(key))
            ) {
                throw new Error("Invalid replay map key");
            }
            keys.push(key);
            return String(keys.length - 1);
        },
        maxArrayLength: 4096,
        maxBinLength: SEED_BYTES,
        maxExtLength: 0,
        maxMapLength: 128,
        maxStrLength: 4096,
    });
    for (const value of decoder.decodeMulti(content)) {
        const restored = restoreData(value, { depth: 0, keys, stringKeys: false });
        if (!isObject(restored)) {
            throw new Error("Replay record is not a map");
        }
        yield restored;
        keys.length = 0;
    }
}
