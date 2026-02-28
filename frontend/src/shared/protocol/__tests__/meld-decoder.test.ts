import { describe, expect, it } from "vitest";
import { decodeMeldCompact } from "../decoders/meld";

describe("decodeMeldCompact", () => {
    describe("chi", () => {
        it("decodes chi 1m-2m-3m seat 0, called 1m", () => {
            // Encoded value from Python: 0
            const result = decodeMeldCompact(0);
            expect(result).toEqual({
                calledTileId: 0, // 1m copy0
                callerSeat: 0,
                fromSeat: 3, // kamicha of seat 0
                meldType: "chi",
                tileIds: [0, 4, 8], // 1m copy0, 2m copy0, 3m copy0
            });
        });

        it("decodes chi 4p-5p-6p seat 1 with different copies", () => {
            // Encoded value from Python: 5429
            const result = decodeMeldCompact(5429);
            expect(result).toEqual({
                calledTileId: 41, // 5p copy1 (called tile)
                callerSeat: 1,
                fromSeat: 0, // kamicha of seat 1
                meldType: "chi",
                tileIds: [36, 41, 44], // 4p copy0, 5p copy1, 6p copy0
            });
        });
    });

    describe("pon", () => {
        it("decodes pon haku seat 2 from seat 0", () => {
            // Encoded value from Python: 20718
            const result = decodeMeldCompact(20718);
            expect(result).toEqual({
                calledTileId: 125, // haku copy 1
                callerSeat: 2,
                fromSeat: 0,
                meldType: "pon",
                tileIds: [124, 125, 126], // haku copies 0,1,2 (missing copy 3)
            });
        });

        it("decodes pon 5m seat 0 from seat 1", () => {
            // Encoded value from Python: 16776
            const result = decodeMeldCompact(16776);
            expect(result).toEqual({
                calledTileId: 16, // 5m copy 0
                callerSeat: 0,
                fromSeat: 1,
                meldType: "pon",
                tileIds: [16, 17, 19], // 5m copies 0,1,3 (missing copy 2)
            });
        });
    });

    describe("added_kan (shouminkan)", () => {
        it("decodes added_kan east wind seat 1 from seat 2", () => {
            // Encoded value from Python: 22321
            const result = decodeMeldCompact(22321);
            expect(result).toEqual({
                calledTileId: 108, // east copy 0
                callerSeat: 1,
                fromSeat: 2,
                meldType: "added_kan",
                tileIds: [108, 109, 110, 111], // east wind all 4 copies
            });
        });
    });

    describe("open_kan (daiminkan)", () => {
        it("decodes open_kan 9s seat 3 from seat 0", () => {
            // Encoded value from Python: 23931
            const result = decodeMeldCompact(23931);
            expect(result).toEqual({
                calledTileId: 106, // 9s copy 2
                callerSeat: 3,
                fromSeat: 0,
                meldType: "open_kan",
                tileIds: [104, 105, 106, 107], // 9s all 4 copies
            });
        });
    });

    describe("closed_kan (ankan)", () => {
        it("decodes closed_kan 1s seat 0", () => {
            // Encoded value from Python: 24360
            const result = decodeMeldCompact(24360);
            expect(result).toEqual({
                calledTileId: null,
                callerSeat: 0,
                fromSeat: null,
                meldType: "closed_kan",
                tileIds: [72, 73, 74, 75], // 1s all 4 copies
            });
        });

        it("decodes closed_kan chun seat 2", () => {
            // Encoded value from Python: 24422
            const result = decodeMeldCompact(24422);
            expect(result).toEqual({
                calledTileId: null,
                callerSeat: 2,
                fromSeat: null,
                meldType: "closed_kan",
                tileIds: [132, 133, 134, 135], // chun all 4 copies
            });
        });

        it("decodes max valid value (24423)", () => {
            // Ankan chun seat 3
            const result = decodeMeldCompact(24423);
            expect(result).toEqual({
                calledTileId: null,
                callerSeat: 3,
                fromSeat: null,
                meldType: "closed_kan",
                tileIds: [132, 133, 134, 135],
            });
        });
    });

    describe("range errors", () => {
        it("throws on negative value", () => {
            expect(() => decodeMeldCompact(-1)).toThrow(RangeError);
        });

        it("throws on value exceeding max (24424)", () => {
            expect(() => decodeMeldCompact(24424)).toThrow(RangeError);
        });

        it("throws on non-integer", () => {
            expect(() => decodeMeldCompact(1.5)).toThrow(RangeError);
        });

        it("throws on NaN", () => {
            expect(() => decodeMeldCompact(NaN)).toThrow(RangeError);
        });
    });
});
