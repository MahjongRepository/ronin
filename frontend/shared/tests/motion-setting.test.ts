import { readMotionSetting } from "@ronin/shared/motion-setting";
import { describe, expect, it } from "vitest";

describe("readMotionSetting", () => {
    it("keeps a setting stored before the discard slide existed, and turns on whatever is missing or malformed", () => {
        expect(
            [
                { animations: false },
                { animations: "no", discardSlide: false },
                { animations: false, discardSlide: false },
                null,
            ].map((stored) => readMotionSetting(stored)),
        ).toEqual([
            { animations: false, discardSlide: true },
            { animations: true, discardSlide: false },
            { animations: false, discardSlide: false },
            { animations: true, discardSlide: true },
        ]);
    });
});
