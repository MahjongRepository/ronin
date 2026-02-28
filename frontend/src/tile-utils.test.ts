import { FIVE_RED_MAN, FIVE_RED_PIN, FIVE_RED_SOU, tile136toString } from "@/tile-utils";
import { describe, expect, test } from "vitest";

describe("tile136toString", () => {
    describe("suit boundaries", () => {
        test("first and last man tiles", () => {
            expect(tile136toString(0)).toBe("1m");
            expect(tile136toString(35)).toBe("9m");
        });

        test("first and last pin tiles", () => {
            expect(tile136toString(36)).toBe("1p");
            expect(tile136toString(71)).toBe("9p");
        });

        test("first and last sou tiles", () => {
            expect(tile136toString(72)).toBe("1s");
            expect(tile136toString(107)).toBe("9s");
        });

        test("first and last honor tiles", () => {
            expect(tile136toString(108)).toBe("1z");
            expect(tile136toString(135)).toBe("7z");
        });

        test("cross-suit boundaries map correctly", () => {
            expect(tile136toString(35)).toBe("9m");
            expect(tile136toString(36)).toBe("1p");
            expect(tile136toString(71)).toBe("9p");
            expect(tile136toString(72)).toBe("1s");
            expect(tile136toString(107)).toBe("9s");
            expect(tile136toString(108)).toBe("1z");
        });
    });

    describe("red fives", () => {
        test("red five man (ID 16) is 0m", () => {
            expect(tile136toString(FIVE_RED_MAN)).toBe("0m");
        });

        test("red five pin (ID 52) is 0p", () => {
            expect(tile136toString(FIVE_RED_PIN)).toBe("0p");
        });

        test("red five sou (ID 88) is 0s", () => {
            expect(tile136toString(FIVE_RED_SOU)).toBe("0s");
        });

        test("IDs adjacent to red fives are normal tiles", () => {
            expect(tile136toString(15)).toBe("4m");
            expect(tile136toString(17)).toBe("5m");
            expect(tile136toString(51)).toBe("4p");
            expect(tile136toString(53)).toBe("5p");
            expect(tile136toString(87)).toBe("4s");
            expect(tile136toString(89)).toBe("5s");
        });
    });

    test("all four copies of a tile map to the same name", () => {
        expect(tile136toString(0)).toBe("1m");
        expect(tile136toString(1)).toBe("1m");
        expect(tile136toString(2)).toBe("1m");
        expect(tile136toString(3)).toBe("1m");
    });

    describe("invalid inputs", () => {
        test("negative ID throws RangeError", () => {
            expect(() => tile136toString(-1)).toThrow(RangeError);
        });

        test("ID above 135 throws RangeError", () => {
            expect(() => tile136toString(136)).toThrow(RangeError);
        });

        test("non-integer throws RangeError", () => {
            expect(() => tile136toString(1.5)).toThrow(RangeError);
        });

        test("NaN throws RangeError", () => {
            expect(() => tile136toString(Number.NaN)).toThrow(RangeError);
        });
    });
});
