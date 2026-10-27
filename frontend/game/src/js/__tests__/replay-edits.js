import { expect } from "vitest";

import wire from "../ronin/wire.js";

/** The index of a replay's first line recording `type`, which the edit needs to exist. */
export function firstLineOf(lines, type) {
    const index = lines.findIndex((line) => line.trim() !== "" && JSON.parse(line).t === type);
    expect(index).toBeGreaterThanOrEqual(0);
    return index;
}

/** The replay with its first draw recorded five times over: the converter takes it, the model refuses a fifth copy. */
export function withUnplayableDraw(text) {
    const lines = text.split("\n");
    const draw = firstLineOf(lines, wire.E.DRAW);
    return [
        ...lines.slice(0, draw + 1),
        ...Array(4).fill(lines[draw]),
        ...lines.slice(draw + 1),
    ].join("\n");
}
