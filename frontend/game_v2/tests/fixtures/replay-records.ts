import { encode } from "@msgpack/msgpack";

import { WIRE_KEY } from "@/shared/protocol";

export function joinBytes(parts: readonly Uint8Array[]): Uint8Array {
    const joined = new Uint8Array(parts.reduce((length, part) => length + part.length, 0));
    let offset = 0;
    for (const part of parts) {
        joined.set(part, offset);
        offset += part.length;
    }
    return joined;
}

function packValue(value: unknown, stringKeys = false): Uint8Array {
    if (Array.isArray(value)) {
        const head =
            value.length < 16
                ? new Uint8Array([144 + value.length])
                : new Uint8Array([220, value.length >> 8, value.length & 255]);
        return joinBytes([head, ...value.map((entry: unknown) => packValue(entry, stringKeys))]);
    }
    if (typeof value !== "object" || value === null || value instanceof Uint8Array) {
        return encode(value);
    }
    const entries = Object.entries(value);
    const head =
        entries.length < 16
            ? new Uint8Array([128 + entries.length])
            : new Uint8Array([222, entries.length >> 8, entries.length & 255]);
    return joinBytes([
        head,
        ...entries.flatMap(([key, entry]) => {
            const id = stringKeys ? key : Number(key);
            const binary =
                id === WIRE_KEY.SEED && typeof entry === "string"
                    ? Uint8Array.from(entry.match(/../g) ?? [], (byte) => Number.parseInt(byte, 16))
                    : entry;
            return [
                encode(id),
                packValue(
                    binary,
                    stringKeys ||
                        id === WIRE_KEY.GAME_SETTINGS ||
                        id === WIRE_KEY.SCORES ||
                        id === WIRE_KEY.SCORE_CHANGES,
                ),
            ];
        }),
    ]);
}

export function encodeReplayRecords(records: readonly unknown[]): Uint8Array {
    return joinBytes(records.map((record) => packValue(record)));
}

export function encodeReplayLines(text: string): Uint8Array {
    return encodeReplayRecords(
        text
            .split("\n")
            .filter((line) => line.trim() !== "")
            .map((line) => {
                try {
                    const value: unknown = JSON.parse(line);
                    return value;
                } catch {
                    return line;
                }
            }),
    );
}
