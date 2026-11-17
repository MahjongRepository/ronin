import { describe, expect, it } from "vitest";

import { handNotation } from "@/entities/replay/model/hand-notation";

const HELD = [32, 0, 17, 16, 20, 68, 100, 72, 76, 80, 132, 120, 124, 121];
const THREE_MAN = 8;
const RED_CHUN = 133;

describe("handNotation", () => {
    it("groups the sorted tiles by suit, a red five as 0 before the other fives, and writes the draw apart at the end", () => {
        expect(handNotation({ drawnTileId: THREE_MAN, tiles: [...HELD, THREE_MAN] }, true)).toBe(
            "10569m9p1238s4457z3m",
        );
        expect(handNotation({ drawnTileId: RED_CHUN, tiles: [...HELD, RED_CHUN] }, true)).toBe(
            "10569m9p1238s4457z7z",
        );
        expect(handNotation({ drawnTileId: null, tiles: HELD }, false)).toBe("15569m9p1238s4457z");
    });
});
