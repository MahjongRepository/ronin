import { describe, expect, it } from "vitest";
import { decodeDraw } from "../decoders/draw";

describe("decodeDraw", () => {
    it("decodes seat 0 tile 0", () => {
        expect(decodeDraw(0)).toEqual({ seat: 0, tileId: 0 });
    });

    it("decodes seat 0 last tile (tile 135)", () => {
        // d = 0 * 136 + 135 = 135
        expect(decodeDraw(135)).toEqual({ seat: 0, tileId: 135 });
    });

    it("decodes seat 1 tile 0", () => {
        // d = 1 * 136 + 0 = 136
        expect(decodeDraw(136)).toEqual({ seat: 1, tileId: 0 });
    });

    it("decodes seat 2 tile 50", () => {
        // d = 2 * 136 + 50 = 322
        expect(decodeDraw(322)).toEqual({ seat: 2, tileId: 50 });
    });

    it("decodes seat 3 last tile (max value 543)", () => {
        // d = 3 * 136 + 135 = 543
        expect(decodeDraw(543)).toEqual({ seat: 3, tileId: 135 });
    });

    it("throws on negative value", () => {
        expect(() => decodeDraw(-1)).toThrow(RangeError);
    });

    it("throws on value >= 544", () => {
        expect(() => decodeDraw(544)).toThrow(RangeError);
    });

    it("throws on non-integer", () => {
        expect(() => decodeDraw(1.5)).toThrow(RangeError);
    });

    it("throws on NaN", () => {
        expect(() => decodeDraw(NaN)).toThrow(RangeError);
    });
});
