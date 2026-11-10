import { describe, expect, it } from "vitest";

import { keyCommand } from "@/views/replay-input";

function command(key: string, code = ""): ReturnType<typeof keyCommand> {
    return keyCommand(new KeyboardEvent("keydown", { code, key }));
}

describe("keyCommand", () => {
    it("steps on the side arrows, moves turns on the up and down arrows and rounds on the page keys", () => {
        expect(
            [
                "ArrowLeft",
                "ArrowRight",
                "ArrowUp",
                "ArrowDown",
                "PageUp",
                "PageDown",
                "Home",
                "End",
            ].map((key) => command(key)),
        ).toEqual([
            "prev",
            "next",
            "prevTurn",
            "nextTurn",
            "prevRound",
            "nextRound",
            "first",
            "last",
        ]);
    });

    it("takes the letters by their key's position, whatever letters the layout types", () => {
        expect([command("р", "KeyH"), command("м", "KeyV"), command(" ", "Space")]).toEqual([
            "hands",
            "view",
            "play",
        ]);
    });
});
