import { describe, expect, it } from "vitest";

import { withoutBlockedPlayback } from "../game-audio.js";

function failingSound(name) {
    return () => ({ play: () => Promise.reject(new DOMException("refused", name)) });
}

describe("withoutBlockedPlayback", () => {
    it("skips a sound the browser blocks before a user gesture, but still rejects any other failure", async () => {
        await expect(
            withoutBlockedPlayback(failingSound("NotAllowedError"))("dapai").play(),
        ).resolves.toBeUndefined();
        await expect(
            withoutBlockedPlayback(failingSound("NotSupportedError"))("dapai").play(),
        ).rejects.toThrow("refused");
    });
});
