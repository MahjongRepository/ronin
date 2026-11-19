import { describe, expect, test } from "vitest";

import { faceViewBox } from "#scripts/tile-ink-centre";

describe("faceViewBox", () => {
    test("moves the viewport with the ink so it lands centred, a blank face unmoved", () => {
        expect(faceViewBox(154.5)).toBe("4.5 0 300 400");
        expect(faceViewBox(145.85)).toBe("-4.15 0 300 400");
        expect(faceViewBox(null)).toBe("0 0 300 400");
    });
});
