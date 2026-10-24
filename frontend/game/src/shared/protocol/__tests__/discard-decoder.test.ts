import { describe, expect, it } from "vitest";

import { decodeDiscard } from "@/shared/protocol/decoders/discard";

describe("decodeDiscard", () => {
    it("decodes plain discard (no flags) - seat 0 tile 0", () => {
        // flag=0, d = 0 * 544 + 0 * 136 + 0 = 0
        expect(decodeDiscard(0)).toEqual({
            isRiichi: false,
            isTsumogiri: false,
            seat: 0,
            tileId: 0,
        });
    });

    it("decodes tsumogiri flag", () => {
        // flag=1 (tsumogiri), seat 0, tile 5: d = 1 * 544 + 0 * 136 + 5 = 549
        expect(decodeDiscard(549)).toEqual({
            isRiichi: false,
            isTsumogiri: true,
            seat: 0,
            tileId: 5,
        });
    });

    it("decodes riichi flag", () => {
        // flag=2 (riichi), seat 1, tile 10: d = 2 * 544 + 1 * 136 + 10 = 1234
        expect(decodeDiscard(1234)).toEqual({
            isRiichi: true,
            isTsumogiri: false,
            seat: 1,
            tileId: 10,
        });
    });

    it("decodes riichi + tsumogiri flags", () => {
        // flag=3 (both), seat 0, tile 0: d = 3 * 544 + 0 = 1632
        expect(decodeDiscard(1632)).toEqual({
            isRiichi: true,
            isTsumogiri: true,
            seat: 0,
            tileId: 0,
        });
    });

    it("decodes max value (2175)", () => {
        // flag=3, seat 3, tile 135: d = 3 * 544 + 3 * 136 + 135 = 2175
        expect(decodeDiscard(2175)).toEqual({
            isRiichi: true,
            isTsumogiri: true,
            seat: 3,
            tileId: 135,
        });
    });

    it("decodes seat boundary (seat 2 tile 0 no flags)", () => {
        // d = 0 * 544 + 2 * 136 + 0 = 272
        expect(decodeDiscard(272)).toEqual({
            isRiichi: false,
            isTsumogiri: false,
            seat: 2,
            tileId: 0,
        });
    });

    it("throws on negative value", () => {
        expect(() => decodeDiscard(-1)).toThrow(RangeError);
    });

    it("throws on value > 2175", () => {
        expect(() => decodeDiscard(2176)).toThrow(RangeError);
    });

    it("throws on non-integer", () => {
        expect(() => decodeDiscard(0.5)).toThrow(RangeError);
    });
});
