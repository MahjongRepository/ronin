import { describe, expect, it } from "vitest";

import { supportsBoardCss } from "@/shared/lib";

function registerProperty(): void {}

function supportsAllButHas(condition: string): boolean {
    return !condition.includes(":has(");
}

describe("supportsBoardCss", () => {
    it("accepts a browser with :has(), container queries, dvh and registered properties", () => {
        expect(supportsBoardCss({ registerProperty, supports: () => true })).toBe(true);
    });

    it("rejects a browser missing :has() or @property, as Firefox before 121 and 128", () => {
        expect(supportsBoardCss({ registerProperty, supports: supportsAllButHas })).toBe(false);
        expect(supportsBoardCss({ supports: () => true })).toBe(false);
    });
});
