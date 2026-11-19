import { afterEach, describe, expect, test } from "vitest";

import { t } from "@/i18n";

afterEach(() => {
    document.documentElement.lang = "";
});

describe("t", () => {
    test("reads the page language from <html lang> and falls back to English for any other value", () => {
        document.documentElement.lang = "ja";
        expect(t("room.start")).toBe("対局開始");

        document.documentElement.lang = "ja-JP";
        expect(t("room.start")).toBe("Start game");
    });
});
