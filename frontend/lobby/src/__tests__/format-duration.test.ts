import { describe, expect, it } from "vitest";

import { formatDuration } from "@/format-duration";

describe("formatDuration", () => {
    it("names hours and minutes from an hour on, minutes and seconds below it", () => {
        expect([formatDuration(3725), formatDuration(3599), formatDuration(42)]).toEqual([
            "1h 2m",
            "59m 59s",
            "42s",
        ]);
    });
});
