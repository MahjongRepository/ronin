import { describe, expect, it } from "vitest";

import { gamePageUrl, isDebugRequested } from "@/shared/config";

describe("isDebugRequested", () => {
    it("turns the debug view on for a bare or truthy debug parameter and off for an off value or none", () => {
        const searches = [
            "?debug",
            "?debug=1",
            "?v=2&debug=true",
            "?debug=0",
            "?debug=False",
            "?v=2",
        ];
        expect(searches.map(isDebugRequested)).toEqual([true, true, true, false, false, false]);
    });
});

describe("gamePageUrl", () => {
    it("opens the game's page under the lobby's game client URL with the current query, the id encoded", () => {
        expect(gamePageUrl("/play", "g 2", "?v=2&debug")).toBe("/play/g%202?v=2&debug");
    });
});
