import { describe, expect, it } from "vitest";

import { shortcutKeysOf } from "@/shared/lib";

const IPAD_AS_MAC =
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15";
const IPHONE =
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
const WINDOWS =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";
const ANDROID =
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36";

describe("shortcutKeysOf", () => {
    it("takes Apple's keys on an iPhone and an iPad naming itself a Mac, the others' elsewhere", () => {
        expect([IPAD_AS_MAC, IPHONE, WINDOWS, ANDROID].map(shortcutKeysOf)).toEqual([
            "apple",
            "apple",
            "other",
            "other",
        ]);
    });
});
