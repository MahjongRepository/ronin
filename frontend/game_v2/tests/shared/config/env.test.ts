import { describe, expect, it } from "vitest";

import { gamePageUrl, isDebugRequested, replayPageUrl } from "@/shared/config";

describe("isDebugRequested", () => {
    it("turns the debug view on for a bare or truthy debug parameter and off for an off value or none", () => {
        const searches = ["?debug", "?debug=1", "?debug=true", "?debug=0", "?debug=False", ""];
        expect(searches.map(isDebugRequested)).toEqual([true, true, true, false, false, false]);
    });
});

describe("gamePageUrl", () => {
    it("opens the game's page under the lobby's game client URL with the current query, the id encoded", () => {
        expect(gamePageUrl("/play", "g 2", "?debug")).toBe("/play/g%202?debug");
    });
});

describe("replayPageUrl", () => {
    it("opens the game's replay from the seat with the id encoded", () => {
        expect(replayPageUrl("g 2", 1)).toBe("/play/history/g%202?seat=1");
        expect(replayPageUrl("g2", null)).toBe("/play/history/g2");
    });
});
