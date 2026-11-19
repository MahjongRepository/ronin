import { readSoundSetting } from "@ronin/shared/sound-setting";
import { describe, expect, it } from "vitest";

describe("readSoundSetting", () => {
    it("reads the stored sound setting, and keeps the sound on for anything else", () => {
        expect(
            [{ sound_on: false }, { sound_on: "no" }, null, []].map((stored) =>
                readSoundSetting(stored),
            ),
        ).toEqual([
            { sound_on: false },
            { sound_on: true },
            { sound_on: true },
            { sound_on: true },
        ]);
    });
});
