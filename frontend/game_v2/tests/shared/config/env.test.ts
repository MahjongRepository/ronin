import { describe, expect, it } from "vitest";

import { isDebugRequested } from "@/shared/config";

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
