import { describe, expect, test } from "vitest";

import { nameParts } from "@/entities/table/lib/name-parts";

describe("nameParts", () => {
    test("keeps a short last word whole with its space, else the last characters, and splits no short name", () => {
        expect(nameParts("Tsumogiri 12")).toEqual({ head: "Tsumogiri", tail: " 12" });
        expect(nameParts("Bot South")).toEqual({ head: "Bot S", tail: "outh" });
        expect(nameParts("Wanjirou")).toEqual({ head: "Wanj", tail: "irou" });
        expect(nameParts("Alice")).toEqual({ head: "Alice", tail: "" });
    });
});
