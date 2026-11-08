import { describe, expect, test } from "vitest";

import { nameParts } from "@/entities/table/lib/name-parts";

describe("nameParts", () => {
    test("keeps the last characters and splits no short name", () => {
        expect(nameParts("ai-tsumogiri-12")).toEqual({ head: "ai-tsumogir", tail: "i-12" });
        expect(nameParts("Wanjirou")).toEqual({ head: "Wanj", tail: "irou" });
        expect(nameParts("Alice")).toEqual({ head: "Alice", tail: "" });
    });
});
