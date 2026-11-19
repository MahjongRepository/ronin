import { afterEach, describe, expect, it } from "vitest";

import { t } from "@/shared/i18n";

afterEach(() => {
    document.documentElement.lang = "";
});

describe("t", () => {
    it("reads the page language from <html lang> and falls back to English for any other value", () => {
        document.documentElement.lang = "ja";
        expect(t("common.lobby")).toBe("ロビー");

        document.documentElement.lang = "ja-JP";
        expect(t("common.lobby")).toBe("Lobby");
    });
});
