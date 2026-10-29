import { describe, expect, test } from "vitest";

import { windLetter, windName } from "@/entities/table/lib/wind-name";

describe("windName", () => {
    test("0 returns East", () => {
        expect(windName(0)).toBe("East");
    });

    test("1 returns South", () => {
        expect(windName(1)).toBe("South");
    });

    test("2 returns West", () => {
        expect(windName(2)).toBe("West");
    });

    test("3 returns North", () => {
        expect(windName(3)).toBe("North");
    });

    test("out-of-range value returns Unknown", () => {
        expect(windName(4)).toBe("Unknown");
        expect(windName(-1)).toBe("Unknown");
    });
});

describe("windLetter", () => {
    test("maps wind indices to single letters", () => {
        expect(windLetter(0)).toBe("E");
        expect(windLetter(1)).toBe("S");
        expect(windLetter(2)).toBe("W");
        expect(windLetter(3)).toBe("N");
    });

    test("out-of-range value returns ?", () => {
        expect(windLetter(4)).toBe("?");
        expect(windLetter(-1)).toBe("?");
    });
});
