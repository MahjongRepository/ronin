import { describe, expect, test } from "vitest";

import { formatRoundName } from "@/entities/table/lib/round-name";

describe("formatRoundName", () => {
    test("formats wind and round number without honba", () => {
        expect(formatRoundName(0, 1, 0)).toBe("East 1");
        expect(formatRoundName(1, 3, 0)).toBe("South 3");
    });

    test("includes honba when non-zero", () => {
        expect(formatRoundName(0, 2, 1)).toBe("East 2, 1 honba");
        expect(formatRoundName(1, 1, 3)).toBe("South 1, 3 honba");
    });

    test("handles all wind values", () => {
        expect(formatRoundName(2, 1, 0)).toBe("West 1");
        expect(formatRoundName(3, 1, 0)).toBe("North 1");
    });
});
