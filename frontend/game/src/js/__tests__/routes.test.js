import { describe, expect, it } from "vitest";

import { STORYBOOK_PAGE, matchRoute, storybookPath } from "../routes.js";

describe("matchRoute", () => {
    it("sends a history path to the replay, not to a game", () => {
        expect(matchRoute("/play/history/g-1")).toEqual({ name: "replay", gameId: "g-1" });
    });

    it("sends the storybook index and its pages to the storybook, not to a game", () => {
        expect(matchRoute("/play/storybook")).toEqual({ name: "storybook", page: "index" });
        expect(matchRoute("/play/storybook/melds")).toEqual({ name: "storybook", page: "melds" });
        expect(matchRoute("/play/storybook/loading")).toEqual({
            name: "storybook",
            page: "loading",
        });
        expect(matchRoute("/play/storybook/unknown")).toBeNull();
    });

    it("sends a single segment under /play to the game and nothing else", () => {
        expect(matchRoute("/play/g-1")).toEqual({ name: "game", gameId: "g-1" });
        expect(matchRoute("/play/g-1/extra")).toBeNull();
        expect(matchRoute("/play/")).toBeNull();
    });
});

describe("storybookPath", () => {
    it.each([
        [STORYBOOK_PAGE.INDEX, "/play/storybook?v=1"],
        [STORYBOOK_PAGE.BOARD, "/play/storybook/board?v=1"],
    ])("keeps the v1 client when linking to %s", (page, path) => {
        expect(storybookPath(page)).toBe(path);
    });
});
